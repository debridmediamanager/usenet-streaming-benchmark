# Why some files here are marked superseded

`results_damage.superseded.json`, `results_obfuscated.superseded.json` and
`results_rar.superseded.json` are the raw output of `corpus5b.py`. Do not read
zurg's rows in them.

`corpus5b.py` identifies the release under test as whatever appeared in the
WebDAV listing while the import ran. zurg was still loading its library when the
baseline listing was taken, so an unrelated release looked new and was probed
instead. zurg's `release_dir` reads `Obfuscated` in all three phases, including
the two where that is the wrong release.

The corrected numbers come from `results_reprobe_r4.json` and
`results_rar_damage_r4.json`, which select the release by name and pick the
largest non-sample video in it. The README quotes only those.

The same misidentification is why `results_rar.superseded.json` cannot be used
for zurg: zurg preserves the archive folder structure, so the first video in its
listing is the 9.5 MB `Sample/` clip. A 16 MB read at offset 100 MB of a 9.5 MB
file is a correct HTTP 416 and not a zurg failure.
