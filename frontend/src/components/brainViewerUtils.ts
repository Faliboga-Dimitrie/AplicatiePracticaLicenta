export type ViewerTissue = 'gm' | 'wm' | 'csf'
export type ViewerArtifactMode = 'mesh'

export type BrainViewerItem = {
  id: string
  name: string
  tissue: ViewerTissue
  mode: ViewerArtifactMode
  objectUrl: string
  /**
   * Keep colors/materials authored inside the GLB. Useful for comparison GLBs
   * where the backend encodes baseline/target colors directly.
   */
  preserveMaterials?: boolean
}

export function inferViewerTissueFromName(name: string, metadataTissue?: unknown): ViewerTissue | null {
  if (metadataTissue === 'gm' || metadataTissue === 'wm' || metadataTissue === 'csf') {
    return metadataTissue
  }

  const lower = name.toLowerCase()
  if (lower.includes('gray') || lower.includes('_gm') || lower.includes('gm_') || lower.includes('-gm')) {
    return 'gm'
  }
  if (lower.includes('white') || lower.includes('_wm') || lower.includes('wm_') || lower.includes('-wm')) {
    return 'wm'
  }
  if (lower.includes('csf') || lower.includes('cerebrospinal')) {
    return 'csf'
  }
  return null
}

export function inferViewerModeFromName(nameOrKind: string): ViewerArtifactMode | null {
  const lower = nameOrKind.toLowerCase()
  if (lower.includes('mesh') || lower.endsWith('.glb')) {
    return 'mesh'
  }
  return null
}

export function isGlbName(name: string, mimeType?: string | null): boolean {
  return name.toLowerCase().endsWith('.glb') || mimeType === 'model/gltf-binary'
}
