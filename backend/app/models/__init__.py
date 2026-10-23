from app.models.user import User
from app.models.ontology import OntologyProject
from app.models.ontology_revision import OntologyRevision
from app.models.entity import Entity
from app.models.entity_instance import EntityInstance
from app.models.relation import Relation
from app.models.logic import LogicRule
from app.models.action import Action
from app.models.v2 import *  # noqa: F401,F403  (registers the v2 tables)

__all__ = ["User", "OntologyProject", "OntologyRevision", "Entity", "EntityInstance", "Relation", "LogicRule", "Action"]
