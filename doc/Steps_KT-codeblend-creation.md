## Steps on KT-codeblend creation
- Date updated: 17 Dec. 2025

### Root branches / commits
1. [epoc-utils/developer](https://github.com/epoc-ed/epoc-utils/tree/developer) / [a9b8957](https://github.com/epoc-ed/epoc-utils/commit/a9b8957e32c44440847e7171bb3919275875adfe)
2. [simple-tem/developer](https://github.com/epoc-ed/simple-tem/tree/developer) / [d06bf39](https://github.com/epoc-ed/simple-tem/commit/d06bf3950a16f234de4557634d8349230d0c6b3f)
3. [GUI/developer](https://github.com/epoc-ed/GUI/tree/developer) / [5aa416f](https://github.com/epoc-ed/GUI/commit/5aa416f20bea1da62a56d594afa716ecf14bb681)

### Rebasing steps with code-fragmentation

More details are seen at each commit message.

1. Pre-running to ensure root branches work
2. Update on [**epoc-utils**] to get property values from JFJ
3. Update on [**simple-tem**] to use additional PyJEM function
4. [**GUI**] Merge the last bug-fixing PR (global constant configuration)
5. [**GUI**] Prepare subroutine for radial integration
6. [**GUI**] Extend calibration scheme for variable measurement conditions
7. [**GUI**] Remove postprocessing from metadata-updater
8. [**GUI**] Prepare postprocessing manager/browser
9. [**GUI**] Prepare auto-beamcentring module, which can work with radial-integration
10. [**GUI**] Activate jfj-spotfinder and display at footer
11. [**GUI**] Activate 3D plotter / Prepare subimage display
12. [**GUI**] Activate PostProcess communicator
13. [**GUI**] Activate utility function
14. [**GUI**] README, feature list, and yaml. Minor bug-fixes and global control of hardcoded variables.

### Logbook of fragmentation
- Test 1, 2, 3: data-acquisition, metadata-compatibility, and XDS-processing
| # | epoc-utils | simple-tem | GUI | Test1 | Test2 | Test3 | Errors | DataID (###\_HHMM) |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- | 
| 1 | [a9b8957](https://github.com/epoc-ed/epoc-utils/commit/a9b8957e32c44440847e7171bb3919275875adfe) | [d06bf39](https://github.com/epoc-ed/simple-tem/commit/d06bf3950a16f234de4557634d8349230d0c6b3f) | [5aa416f](https://github.com/epoc-ed/GUI/commit/5aa416f20bea1da62a56d594afa716ecf14bb681) | passed | passed | passed | - | 000-0757 |
| 2 | [f489726](https://github.com/epoc-ed/epoc-utils/commit/f489726fec85b231a899ada33568b898ddb10ce0) | d06bf39 | 5aa416f | passed | passed | passed | - | 001-0806 |
| 3 | f489726 | [750fd05](https://github.com/epoc-ed/simple-tem/commit/750fd05d0654a43f97a02aa04f7b940e188739a2) | 5aa416f | passed | passed | passed | - | 002-0809 |
| 4 | f489726 | 750fd05 | [736543f](https://github.com/epoc-ed/GUI/commit/736543f91b0cbe1b123eaf1143e0a7e4447298e0) | passed | passed | passed | - | 003-0829 |
| 5 | f489726 | 750fd05 | [f67826d](https://github.com/epoc-ed/GUI/commit/f67826d4d4dd193b6725479e394ce4b8c2353894) | passed | passed | passed | - | 004-0846 |
| 6 | f489726 | 750fd05 | [ae0f4e4](https://github.com/epoc-ed/GUI/commit/ae0f4e4055b4f445718c9d43f7d226a930ae69b0) | passed | passed | passed | - | 005-0903 |
| 7 | f489726 | 750fd05 | [f9ec69e](https://github.com/epoc-ed/GUI/commit/f9ec69effd86f711c26f6c599ee4447600f46066) | passed | passed | passed | - | 037-1401 |
| 8 | f489726 | 750fd05 | [aa2773f](https://github.com/epoc-ed/GUI/commit/aa2773f45d72f303bacef6eefcbffbb0f82f2f51) | passed | passed | passed | - | 038-1443 |
| 9 | f489726 | 750fd05 | [1cb0089](https://github.com/epoc-ed/GUI/commit/1cb0089493880eb21b1df5de77a3d0b345beec69) | passed | passed | passed | - | 039-1546 |
| 10 | f489726 | 750fd05 | [d3b98d7](https://github.com/epoc-ed/GUI/commit/d3b98d79b83571df86b93ca54370bde4b44a990e) | passed | passed | passed | - | 040-1642 |
| 11 | f489726 | 750fd05 | [9e410b5](https://github.com/epoc-ed/GUI/commit/9e410b5a59e102c03797dca6066646c11f2b50b4) | passed | passed | passed | - | 041-1835 |
| 12 | f489726 | 750fd05 | [41a7a90](https://github.com/epoc-ed/GUI/commit/41a7a907cf16a6c3937f0a1a19d4df8cac43ef93) | passed | passed | passed | - | 049-2032 |
| 13 | f489726 | 750fd05 | [98ab0e3](https://github.com/epoc-ed/GUI/commit/98ab0e342814a75410204344f72ff39810841c81) | passed | passed | passed | - | 050-1324 |
| 14 | f489726 | 750fd05 | The latest on 17 Dec 2025 (commit hash not yet known) | - | - | - | - | - | - |
