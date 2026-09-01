# Round 6

A different question from rounds 3 to 5. Those measured how fast a server
serves bytes. This one measures what it publishes: given identical NZBs, what
appears on the filesystem, under what names, and does it read back.

Each target starts from an empty library, is given the same five NZBs, and is
then mounted read-only over rclone with identical flags and the VFS cache off,
so `tree` walks the server's own listing. Isolation is unchanged. One server
holds the news account at a time, imports included.

## Files here

```
results_tree_r6.json    the run: imports, settle, listings, read-back per release
report_data.json        the tally, scored against the NZB contents
tree.<target>.txt       the tree dump quoted in the README
tree.<target>.json      the same dump, machine readable, with byte sizes
tree.<target>.native.*  the server's own mount where it ships one (zurg, decypharr)
nzb_survey.log/.json    retrievability of every candidate release, measured first
statlat.txt             STAT latency of both news hosts
altmount_control.txt    the controlled re-run that ruled out the news host
versions.json           the commit each target was built from
corpus.txt              the five NZBs, in import order
tree_r6_final.log       raw stdout of the run
```

## The corpus changed mid-round, twice, and both times for a reason

The first corpus carried `ToyStory5Damaged.nzb`, which is deliberately corrupt.
It was dropped because this round is about healthy input.

Its replacement, `DoomsdayRar.nzb`, was then also dropped. Every one of its
articles is present on the server, and it is still broken: it carries `.rar`
plus `.r28` through `.r93` and is missing `.r00` through `.r27`. Twenty eight of
its ninety four volumes were never posted, so no server can extract it. STAT
answers whether articles are on the server. It does not answer whether the
release is whole. Those are different questions and conflating them cost a run.

`MandaloriaREMUX.nzb` replaced it. The DoomsdayRar dumps are not published here
because the run that produced them used a different corpus, but the behaviour
was worth recording: zurg published the release as a directory of 66 raw
volumes, and nzbdav and decypharr omitted it entirely.

## Four candidate releases in the pool are rotted

`nzb_survey.log` has the measurements. `Penguin.S01.nzb` returned 0 of 387
sampled articles. Two TLOU releases returned about 39%. Any of them in the
corpus would have produced five servers failing the same release, which reads
as a server bug rather than as dead content.

## Why the roots are fixed rather than discovered

An earlier pass discovered each server's WebDAV root at run time and got a
different depth for different servers. Two were dumped at their whole namespace
and two at only their content directory, which makes the entry counts
incomparable. `tree_r6.py` now fixes the root per target to where an imported
release lands, and lists the top of the namespace separately.
