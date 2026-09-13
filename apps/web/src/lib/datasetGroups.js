export function datasetComparison(dataset) {
  return dataset?.metadata_json?.dataset_comparison || {};
}

export function hasDatasetComparison(dataset) {
  const comparison = datasetComparison(dataset);
  return Boolean(comparison.dataset_group_id || comparison.dataset_role || comparison.comparison_status);
}

export function datasetGroupId(dataset) {
  const comparison = datasetComparison(dataset);
  if (comparison.dataset_group_id) return comparison.dataset_group_id;
  if (dataset?.file_hash) return `dataset-hash-${dataset.file_hash}`;
  return `dataset-group-${dataset.id}`;
}

export function datasetRole(dataset) {
  return datasetComparison(dataset).dataset_role || "primary";
}

export function datasetStatus(dataset) {
  return datasetComparison(dataset).comparison_status || "primary";
}

export function groupDatasetsForDisplay(datasets) {
  const groupsById = new Map();
  const sortedDatasets = [...(datasets || [])].sort((a, b) => {
    const aTime = new Date(a.created_at || 0).getTime();
    const bTime = new Date(b.created_at || 0).getTime();
    return aTime - bTime;
  });

  for (const dataset of sortedDatasets) {
    const groupId = datasetGroupId(dataset);
    if (!groupsById.has(groupId)) {
      groupsById.set(groupId, {
        id: groupId,
        primary: null,
        variants: [],
        status: "primary",
        legacyHashGroup: !hasDatasetComparison(dataset) && Boolean(dataset?.file_hash),
      });
    }

    const group = groupsById.get(groupId);
    if (!group.primary || (hasDatasetComparison(dataset) && datasetRole(dataset) === "primary" && dataset.id !== group.primary.id)) {
      if (group.primary) group.variants.push(group.primary);
      group.primary = dataset;
    } else {
      group.variants.push(dataset);
    }
  }

  return Array.from(groupsById.values()).map((group) => {
    if (!group.primary) {
      group.primary = group.variants.shift();
    }
    const variantStatuses = group.variants.map(datasetStatus);
    const exactDuplicateGroup =
      group.legacyHashGroup && group.variants.length > 0 && group.variants.every((variant) => variant.file_hash === group.primary?.file_hash);
    return {
      ...group,
      status: exactDuplicateGroup ? "duplicate" : variantStatuses.includes("similar") ? "similar" : datasetStatus(group.primary),
      hiddenDuplicateCount: exactDuplicateGroup ? group.variants.length : 0,
      variants: group.variants.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0)),
    };
  });
}

export function filterDatasetGroups(groups, query) {
  const normalize = (value) => String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLocaleLowerCase("vi");
  const needle = normalize(query);
  if (!needle) return groups || [];
  return (groups || []).filter((group) =>
    [group.primary, ...(group.variants || [])].some((dataset) =>
      normalize(dataset?.original_name).includes(needle)
    )
  );
}
