# OSF registration: the analysis frozen before the remaining runs

**Not used.** On 23 Oct 2026 the authors decided not to register on OSF (changelog of `PREREGISTRATION.md`). The analysis frozen for the remaining runs is the code at commit `1b7f776`; the runs use the documentation-only commit that adds this note, pushed to GitHub before any run. The fingerprints below remain the record of the frozen files (the one for `PREREGISTRATION.md` matches that commit), and the registration steps further down were not carried out.

Purpose as written: give an outside, timestamped record that the analysis was fixed before the data of the runs that have not happened yet: mistral-medium-3-5's and claude-sonnet-5-5's main study, nemotron-3-super's exploratory run, and Amendment 2's checks. Our own record so far is the git history, plus GitHub's continuous-integration timestamps for the registration commit (`8077392`, 2026-10-20 01:17 UTC) and Amendment 1 (`b15cc3c`, 2026-10-20 14:57 UTC).

## State of data collection at registration (as of 23 October 2026)

| Run | State |
|---|---|
| Protocol checks (768 episodes, 19 Oct) | done; not study data |
| Pilot (1,200 episodes, 20 Oct) | done; decided go/no-go only (GO) |
| Main study, gpt-oss-120b (5,280 episodes) | done; results examined (interim look) |
| Secondary run, gpt-oss-120b (3,100 episodes) | done; results examined |
| Main study, mistral-medium-3-5 and claude-sonnet-5-5 | **not run** |
| Exploratory run, nemotron-3-super | **not run** |
| Amendment 2's checks, gpt-oss-120b (`configs/runs/robustness.yaml`) | **not run** |

## What is frozen

The repository at the latest commit on `main` when you register (record its full hash on OSF; `git rev-parse HEAD` prints it). Check first that every fingerprint below still matches: `shasum -a 256 <file>` for each, or the snippet in the next section. The files that define the tests and the remaining runs, and the data already collected, are fingerprinted here so that any later change can be detected (SHA-256; recompute with `shasum -a 256 <file>`). The data logs are not in the repository; they are released with the paper.

| File | SHA-256 |
|---|---|
| `prereg/PREREGISTRATION.md` | `c35a97af2b485c8eeb8a94a3dc25362a1970ab314c55e165f7de877902d82691` |
| `prereg/PREREGISTRATION-registered-2026-10-19.md` | `72540fb8e5b7349ad1ac1abde1f913807978c03cc8d144aa112d4b1abb8398bb` |
| `prereg/AMENDMENT-1.md` | `6cc778220419b7eb49053c17bae22134d9427d7cdb599c6ecb78068737674fca` |
| `prereg/AMENDMENT-2.md` | `0063f732d35f6a6aed33966a98c38baf3cdf071fc71a34b1b19b71d7ed6b82b4` |
| `src/fplp/analysis/hypotheses.py` | `44f45fa204cf320c0924d09c3fb633b56fc3ba5b1ef69737f8c4ae1157b35529` |
| `src/fplp/analysis/robustness.py` | `20db5d81590e693923a2fbaf06f00a8b4fc1ad85338e5767972a6b40c0bce499` |
| `src/fplp/analysis/multiplicity.py` | `8008fc362d3561074699856977b15bde3147f7f2fd07413436a78d63c5b612e5` |
| `src/fplp/analysis/reference.py` | `0003524a5a637c4dc6beff154e88db57a24e7e342e428aa5382253c3e0135951` |
| `src/fplp/metrics.py` | `67319289f4ccb858fd320b8d4453c03aa00e5a69f9bd46b9718f7ed95c9b2159` |
| `configs/runs/main.yaml` | `12747dbdebd51784d520a5c3f60ecff65917a8a3d66d54c463d6717cb2357222` |
| `configs/runs/robustness.yaml` | `8d1089c9bb67220d8162a5d4e287b4f5f962d295e83a02ce661ddeeb31a9d775` |
| `configs/runs/exploratory.yaml` | `72d325ac190b69baff21617b0203a17c069c2b64d0e325d3266dea31ec7f57af` |
| `configs/models.yaml` | `1cda2a1a39c630e165715501fd61f422142124433166aa0c9f50b79838a696cf` |
| `data/raw/pilot/gpt-oss-120b.jsonl` | `c1a25cab72cf9094298033506cfe2b71f64ca364fc4a28450824ceffeb80cd8c` |
| `data/raw/pilot/claude-sonnet-5-5.jsonl` | `263b6c31afb118496f255f57f663c77dff9287e3dbce71793aacec5b20363117` |
| `data/raw/main/gpt-oss-120b.jsonl` | `a959fa1637798261631468d825ad62b6f5c7240ecb1b32eb0e58a387ccdd659d` |
| `data/raw/secondary/gpt-oss-120b.jsonl` | `39525d6f96fcdeb5ae378e98415510457ff323aa8cb2f034b3443879f985e5a5` |

## How to register (about 30 minutes; needs an OSF account)

0. Verify the fingerprints from the repository root:

   ```sh
   python3 -c "import hashlib,re,pathlib; t=pathlib.Path('prereg/OSF-REGISTRATION.md').read_text(); r=re.findall(r'\| \`([^\`]+)\` \| \`([0-9a-f]{64})\` \|',t); print([f for f,h in r if hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest()!=h] or 'all match')"
   ```

1. On osf.io, create a project (it can stay private) and upload: `prereg/PREREGISTRATION.md`, `prereg/PREREGISTRATION-registered-2026-10-19.md`, `prereg/AMENDMENT-1.md`, `prereg/AMENDMENT-2.md`, this file, and a zip of the repository at the frozen commit (`git archive --format=zip -o fplp-frozen.zip <commit>`).
2. Choose "New registration", template "Open-Ended Registration". In the summary, paste the first two sections of this file and the frozen commit hash.
3. Set an embargo that lasts past the review period. The registration stays private but is timestamped by OSF at once.
4. For double-blind review, create an anonymized view-only link to the registration and cite that link in the paper; replace it with the public registration for the camera-ready version.
5. Register before starting any run listed as "not run" above, and record the registration date in the pre-registration changelog.
