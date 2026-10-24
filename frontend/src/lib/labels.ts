/** "CustomerOrder" -> "Customer Order", "BOMLine" -> "BOM Line". */
export const typeLabel = (name: string) => name.replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2').replace(/([a-z0-9])([A-Z])/g, '$1 $2')
