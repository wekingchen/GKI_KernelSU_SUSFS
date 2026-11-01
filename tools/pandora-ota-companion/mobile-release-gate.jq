# Accept first delivery with the app-created capture tag, or a *previously
# authenticated* Draft Release that GitHub retagged to untagged-* after a PATCH.
# Never trust arbitrary untagged releases: the exact attachment ID and SHA256
# must already exist as complete, line-bound server intake receipt fields.
def hasline($line): ((.body // "") | split("\n") | index($line)) != null;
(
  .id == $id
  and .draft == true
  and .name == "Pandora OS4 OTA capture — private intake"
  and (
    ((.tag_name // "") | startswith("pandora-ota-capture-"))
    or (
      ((.tag_name // "") | startswith("untagged-"))
      and hasline("MOBILE_ASSET_ID=\($asset)")
      and hasline("MOBILE_SOURCE_SHA256=\($sha)")
      and (((.body // "") | split("\n") | any(startswith("MOBILE_OTA_INTAKE="))))
    )
  )
)
