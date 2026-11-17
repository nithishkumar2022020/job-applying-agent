# Discovery connector research

Reviewed 17 November 2026. This is an implementation record, not a claim of complete India market coverage.

| Project | Assessment | Integration |
| --- | --- | --- |
| [JobSpy](https://github.com/speedyapply/JobSpy) | MIT; active repository, approximately 4,750 GitHub stars at review. Version 1.4.1 tested locally. Public Naukri and Indeed searches each returned ten India listings in the initial probe. | Four bounded India queries, 30 results each: Naukri GenAI/Python and Indeed graduate/GenAI. No account, proxies, applications or block bypass. Portal identity/pay claims require review. |
| [openroles](https://github.com/aranculleton/openroles) | MIT; version 0.5.1. New, small project, so pinned and wrapped with normalization tests. Supports fifteen ATS families, but support in the library does not prove a particular employer is readable. | Rippling and Genios AI live-tested. Reads employer feeds, descriptions and work arrangements. Imports detailed India technical roles with at most 40 detail requests per board. Its robots/rate-limit checks remain enabled. |
| [Career Radar](https://github.com/haoawake/career-radar) | Large employer directory and enterprise ATS examples; US-oriented. No license declared at review. | Research reference for employer URLs only; no source code or US country facets copied. Employer URLs were tested separately. |

## Live additions

- Direct Greenhouse boards: Groww, Druva, Twilio, InMobi and Elastic.
- Direct Lever board: Mindtickle.
- Through openroles: Rippling's employer board and Genios AI's board.
- Through JobSpy: Naukri and Indeed India query searches, with descriptions, reported experience and published INR salary when available.

The first probe returned 13 detailed India roles across the two Rippling-hosted employers. The six additional Greenhouse/Lever feeds each returned Indian listings. These are observed probe counts, not promises about the next scan or suitable fresher jobs.

## Enterprise ATS findings

Workday is now supported by the openroles adapter, but employer connectivity remains separate. Accenture/Adobe requests encountered HTTP 429 while checking source rules. A later check also encountered 429 for HPE, NVIDIA and Salesforce. Earlier graduate-only probes returned zero for several of those boards and Mastercard; zero was not treated as proof of broad usable coverage. These candidate boards are disabled in the registry and remain manual links. They are not counted among active automated sources.

WITCH graduate pathways are still dated research leads, not automated vacancy feeds. Adding an ATS adapter does not turn a closed TCS drive or an inaccessible Wipro/Infosys portal into a live opening.

## Operation and limitations

Install the pinned optional dependencies with `python -m pip install '.[discovery]'`. The scheduled workflow does this automatically. The launch scripts use `.venv/bin/python` when present. Missing optional dependencies produce a source failure with an installation message, while other sources continue.

Search keywords and source bounds are in `sources.json`. These define discovery coverage; selectable dashboard filters then operate on the imported inventory. India is specified for portal searches and independently checked before storage. State abbreviations such as DL, KA, AP and TS are expanded so location controls work.

Portal salary is annualized only for published INR monthly/yearly amounts. Missing pay remains unknown; remote/hybrid fields are preserved where provided. Descriptions and experience are source claims and can need verification. Do not treat a broad search hit as a confirmed fit.

Repeated portal queries can find the same job. Existing deduplication merges matching company/title/location/host records; the source-run history retains fetched counts. Cross-host reposts may remain separate. Source counts and successful import counts are different from the number of eligible applications.

Do not add a manual link to the active feed count. HTTP failures and blocked sources must remain visible, and must not be represented as scans that found no jobs.
