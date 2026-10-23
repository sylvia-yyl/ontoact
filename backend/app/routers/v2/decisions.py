"""Decision packages: create from a run, review, apply, revert; plus grounded candidate explanations."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from app.deps import get_db, get_current_user, require_editor
from app.models.ontology import OntologyProject
from app.models.v2.decision import (DecisionPackage,
    DecisionPackageAction, DecisionPackageEvidence, DecisionPackageEvent, DecisionOutbox)
from app.models.v2.scenario import ScenarioResource, ScenarioRun, ScenarioRunArtifact
from app.services.v2 import decision_packages as package_service
from app.services.v2.decision_packages import DecisionPackageError, package_digest, stable_digest, transition

router = APIRouter(dependencies=[Depends(get_current_user)])


def scope(db, oid, user):
    obj = db.get(OntologyProject, oid)
    if not obj or (user.role != 'admin' and obj.created_by != user.id):
        raise HTTPException(404, 'Ontology not found or not accessible')
    return obj


class PackageActionInput(BaseModel):
    action_type_id: str = Field(min_length=1, max_length=100)
    invocation: dict
    expected_edits: list[dict] = Field(default_factory=list, max_length=500)
    external_effect_class: Literal["none", "reversible", "irreversible"] = "none"


class PackageEvidenceInput(BaseModel):
    evidence_type: Literal["artifact", "impact_path", "metric", "constraint", "object"]
    reference: dict
    # Run artifacts use the canonical "sha256:<hex>" form; packages store the bare hex.
    content_digest: str = Field(pattern=r"^(sha256:)?[0-9a-f]{64}$")

    @field_validator("content_digest")
    @classmethod
    def _bare_digest(cls, value: str) -> str:
        return value.removeprefix("sha256:")


class PackageCreateInput(BaseModel):
    scenario_id: str
    scenario_revision: int = Field(ge=0)
    run_id: str
    title: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=10000)
    actions: list[PackageActionInput] = Field(min_length=1, max_length=30)
    evidence: list[PackageEvidenceInput] = Field(min_length=1, max_length=100)


class PackageFromRunInput(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    rationale: str = Field(min_length=1, max_length=10000)


class PackageCommandInput(BaseModel):
    expected_etag: int = Field(ge=1)
    request_id: str = Field(min_length=1, max_length=200)


class PackageTransitionInput(BaseModel):
    # Apply and revert are not plain transitions: they run through :apply / :revert,
    # which perform the Scenario merge, so a package cannot be marked applied by hand.
    event: Literal["submit", "approve", "reject", "revise", "supersede"]
    expected_etag: int = Field(ge=1)
    request_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=4000)


def package_json(db, item):
    actions = db.query(DecisionPackageAction).filter_by(package_id=item.id).order_by(DecisionPackageAction.sequence).all()
    evidence = db.query(DecisionPackageEvidence).filter_by(package_id=item.id).all()
    events = db.query(DecisionPackageEvent).filter_by(package_id=item.id).order_by(DecisionPackageEvent.sequence).all()
    outbox = db.query(DecisionOutbox).filter_by(package_id=item.id).all()
    return {"id": item.id, "scenario_id": item.scenario_id, "scenario_revision": item.scenario_revision,
            "run_id": item.run_id, "title": item.title, "rationale": item.rationale, "status": item.status,
            "content_digest": item.content_digest, "preview_digest": item.preview_digest, "etag": item.etag,
            "created_by": item.created_by, "reviewed_by": item.reviewed_by, "applied_decision_id": item.applied_decision_id,
            "outbox": [{"id": row.id, "action_id": row.action_id, "delivered": row.delivered, "attempts": row.attempts} for row in outbox],
            "actions": [{"id": row.id, "sequence": row.sequence, "action_type_id": row.action_type_id,
                         "invocation": row.invocation, "expected_edits": row.expected_edits,
                         "external_effect_class": row.external_effect_class, "receipt": row.receipt} for row in actions],
            "evidence": [{"id": row.id, "evidence_type": row.evidence_type, "reference": row.reference,
                          "content_digest": row.content_digest} for row in evidence],
            "events": [{"sequence": row.sequence, "event_type": row.event_type, "actor_id": row.actor_id,
                        "reason": row.reason, "request_id": row.request_id} for row in events]}


@router.get('/{oid}/decision-packages')
def list_packages(oid: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    scope(db, oid, user)
    return {"packages": [package_json(db, row) for row in db.query(DecisionPackage).filter_by(ontology_id=oid).order_by(DecisionPackage.created_at.desc()).all()]}


@router.post('/{oid}/decision-packages')
def create_package(oid: str, body: PackageCreateInput, db: Session = Depends(get_db), user=Depends(require_editor)):
    scope(db, oid, user)
    scenario = db.query(ScenarioResource).filter_by(id=body.scenario_id, ontology_id=oid).first()
    run = db.query(ScenarioRun).filter_by(id=body.run_id, scenario_id=body.scenario_id).first()
    if not scenario or not run:
        raise HTTPException(422, "Scenario or Run does not belong to this ontology")
    if run.status != "completed" or run.revision != body.scenario_revision or scenario.head_revision != body.scenario_revision:
        raise HTTPException(409, "Run is incomplete or its Scenario revision is stale")
    artifacts = {row.id: row for row in db.query(ScenarioRunArtifact).filter_by(run_id=run.id).all()}
    for evidence in body.evidence:
        if evidence.evidence_type in {"artifact", "impact_path"}:
            artifact_id = str(evidence.reference.get("artifact_id", ""))
            if artifact_id not in artifacts or artifacts[artifact_id].content_digest.removeprefix("sha256:") != evidence.content_digest:
                raise HTTPException(422, "Evidence artifact or digest is invalid")
    return _insert_package(db, oid, user, scenario_id=body.scenario_id, scenario_revision=body.scenario_revision, run_id=body.run_id,
                           title=body.title, rationale=body.rationale, actions=[row.model_dump(mode="json") for row in body.actions],
                           evidence=[row.model_dump(mode="json") for row in body.evidence])


def _insert_package(db, oid, user, *, scenario_id, scenario_revision, run_id, title, rationale, actions, evidence):
    digest = package_digest(ontology_id=oid, scenario_id=scenario_id, scenario_revision=scenario_revision,
        run_id=run_id, title=title, rationale=rationale, actions=actions, evidence=evidence)
    item = DecisionPackage(ontology_id=oid, scenario_id=scenario_id, scenario_revision=scenario_revision,
        run_id=run_id, title=title, rationale=rationale, content_digest=digest,
        preview_digest=stable_digest([row["expected_edits"] for row in actions]), created_by=user.id)
    db.add(item); db.flush()
    for sequence, row in enumerate(actions):
        db.add(DecisionPackageAction(package_id=item.id, sequence=sequence, **row))
    for row in evidence:
        db.add(DecisionPackageEvidence(package_id=item.id, **row))
    db.add(DecisionPackageEvent(package_id=item.id, sequence=0, event_type="created", actor_id=user.id,
        reason="", request_id=f"create:{item.id}", after_digest=digest))
    db.commit()
    return package_json(db, item)


def _package_error(exc: DecisionPackageError):
    raise HTTPException(exc.status_code, {"code": exc.code, "message": str(exc)}) from exc


@router.post('/{oid}/scenario-study-runs/{run_id}/decision-packages')
def create_package_from_run(oid: str, run_id: str, body: PackageFromRunInput, db: Session = Depends(get_db), user=Depends(require_editor)):
    """Create a draft whose edits the server compiles from the run's pinned data view."""
    scope(db, oid, user)
    run = db.get(ScenarioRun, run_id)
    scenario = db.query(ScenarioResource).filter_by(id=run.scenario_id, ontology_id=oid).first() if run else None
    if not run or not scenario:
        raise HTTPException(404, {"code": "run_not_found", "message": "Run not found"})
    if run.status != "completed":
        raise HTTPException(409, {"code": "run_not_complete", "message": "Run is not complete"})
    if scenario.head_revision != run.revision:
        raise HTTPException(409, {"code": "stale_scenario_revision", "message": "Scenario changed after this run"})
    try:
        actions, evidence, label = package_service.compile_package_actions(db, run, oid, body.candidate_id, user)
    except DecisionPackageError as exc:
        _package_error(exc)
    return _insert_package(db, oid, user, scenario_id=scenario.id, scenario_revision=run.revision, run_id=run.id,
                           title=body.title or label, rationale=body.rationale, actions=actions, evidence=evidence)


def _locked_package(db, oid, package_id):
    item = db.query(DecisionPackage).filter_by(id=package_id, ontology_id=oid).with_for_update().first()
    if not item:
        raise HTTPException(404, "Decision package not found")
    return item


@router.post('/{oid}/decision-packages/{package_id}:apply')
def apply_package(oid: str, package_id: str, body: PackageCommandInput, db: Session = Depends(get_db), user=Depends(require_editor)):
    scope(db, oid, user)
    item = _locked_package(db, oid, package_id)
    try:
        delivery = package_service.apply_package(db, item, user, expected_etag=body.expected_etag, request_id=body.request_id)
    except DecisionPackageError as exc:
        _package_error(exc)
    return {"package": package_json(db, db.get(DecisionPackage, package_id)), "delivery": delivery}


@router.post('/{oid}/decision-packages/{package_id}:deliver-outbox')
def deliver_package_outbox(oid: str, package_id: str, db: Session = Depends(get_db), user=Depends(require_editor)):
    scope(db, oid, user)
    item = _locked_package(db, oid, package_id)
    if item.status != "applied":
        raise HTTPException(409, {"code": "invalid_transition", "message": "Only applied packages have external effects"})
    return {"package": package_json(db, item), "delivery": package_service.deliver_outbox(db, item)}


@router.post('/{oid}/decision-packages/{package_id}:revert')
def revert_package(oid: str, package_id: str, body: PackageCommandInput, db: Session = Depends(get_db), user=Depends(require_editor)):
    scope(db, oid, user)
    item = _locked_package(db, oid, package_id)
    try:
        result = package_service.revert_package(db, item, user, expected_etag=body.expected_etag, request_id=body.request_id)
    except DecisionPackageError as exc:
        _package_error(exc)
    return {"package": package_json(db, db.get(DecisionPackage, package_id)), **result}


@router.post('/{oid}/decision-packages/{package_id}/transition')
def transition_package(oid: str, package_id: str, body: PackageTransitionInput, db: Session = Depends(get_db), user=Depends(require_editor)):
    scope(db, oid, user)
    item = db.query(DecisionPackage).filter_by(id=package_id, ontology_id=oid).with_for_update().first()
    if not item:
        raise HTTPException(404, "Decision package not found")
    duplicate = db.query(DecisionPackageEvent).filter_by(package_id=item.id, request_id=body.request_id).first()
    if duplicate:
        return package_json(db, item)
    try:
        before, target = transition(item, body.event, user.id, expected_etag=body.expected_etag, reason=body.reason)
    except DecisionPackageError as exc:
        raise HTTPException(exc.status_code, {"code": exc.code, "message": str(exc)}) from exc
    sequence = db.query(DecisionPackageEvent).filter_by(package_id=item.id).count()
    db.add(DecisionPackageEvent(package_id=item.id, sequence=sequence, event_type=body.event, actor_id=user.id,
        reason=body.reason, request_id=body.request_id, before_digest=before, after_digest=item.content_digest))
    db.commit()
    return package_json(db, item)


@router.get('/{oid}/scenario-study-runs/{run_id}/explanations')
def list_explanations(oid: str, run_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    scope(db, oid, user)
    rows = db.query(ScenarioRunArtifact).filter(ScenarioRunArtifact.run_id == run_id, ScenarioRunArtifact.artifact_type.like('explanation:%')).all()
    return {"explanations": [row.manifest_json for row in rows]}


@router.post('/{oid}/scenario-study-runs/{run_id}/candidates/{candidate_id}:explain')
def explain_candidate(oid: str, run_id: str, candidate_id: str, db: Session = Depends(get_db), user=Depends(require_editor)):
    """Ask the configured LLM to explain one candidate from this run's evidence, then verify it."""
    from app.services.v2.decision_explanations import ExplanationError, explain
    scope(db, oid, user)
    run = db.get(ScenarioRun, run_id)
    if not run or not db.query(ScenarioResource).filter_by(id=run.scenario_id, ontology_id=oid).first():
        raise HTTPException(404, {"code": "run_not_found", "message": "Run not found"})
    try:
        node_key, _, candidate = package_service.find_candidate(db, run, candidate_id)
        result = explain(run.result_manifest["nodes"][node_key]["outputs"], candidate)
    except DecisionPackageError as exc:
        _package_error(exc)
    except ExplanationError as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": str(exc)}) from exc
    artifact_type = f"explanation:{candidate_id}"[:80]
    row = db.query(ScenarioRunArtifact).filter_by(run_id=run.id, artifact_type=artifact_type).first()
    digest = stable_digest(result)
    if row:
        row.manifest_json, row.content_digest = result, digest
    else:
        db.add(ScenarioRunArtifact(run_id=run.id, artifact_type=artifact_type, manifest_json=result, content_digest=digest))
    db.commit()
    return result
