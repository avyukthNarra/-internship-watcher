# Coverage review: direct internship boards

## Method

Downloaded the current SimplifyJobs and vanshb03 `listings.json` files on 2026-11-25 into a temporary analysis directory. Counted listings posted from 2026-07-28 through 2026-11-25 that matched the top-level season terms in `config.json` (`Fall 2026`, `Winter 2027`, `Spring 2027`, `Summer 2027`), regardless of active status. Role relevance used any configured `alert_channels[].roles` keyword or the `Software`, `AI/ML/Data`, `Hardware`, and `Quant` categories. Kept US listings with an explicit US marker or US state location and excluded non-US-only locations. Exact job URLs were deduplicated across feeds where possible; vanshb03 shortlinks were counted separately because the listing URLs do not expose a canonical URL.

Classified application systems from listing URLs as Greenhouse, Lever, Ashby, Workday, or other. For Greenhouse, Lever, and Ashby, a company needed at least three relevant listings overall; every board slug exposed by those listings was URL-derived and verified. Added verified boards, skipping boards that were empty, mismatched, or already configured. Ranked Workday companies by relevant volume, verified the top 15, and added them to reach the 20-board Workday cap. `company_keywords` additions use whole-word matching in `company_matches` and route aggregate-feed postings to TOP.

Counts are feed observations for the 120-day window, not a count of current openings on the ATS API. ATS verification confirms the board API responds with the expected schema; it does not count relevant roles.

## Added boards

| Company | ATS | Relevant postings / 120d | Board |
|---|---|---:|---|
| Allen Control Systems | ashby | 3 | `allen-control-systems` |
| Amplify | ashby | 6 | `amplify` |
| Apex | ashby | 3 | `apex-technology-inc` |
| DriveWealth | ashby | 11 | `drivewealth` |
| Fab2 | ashby | 14 | `fab2` |
| GrayMatter Robotics | ashby | 4 | `graymatter-robotics` |
| Hadrian | ashby | 4 | `hadrian-automation` |
| ibotta | ashby | 4 | `ibotta` |
| Illumio | ashby | 6 | `illumio` |
| Integrate | ashby | 3 | `integrate` |
| Klaviyo | ashby | 9 | `f40d14d9-07f4-403d-802b-37453deccf0a` |
| Metalenz | ashby | 3 | `metalenz` |
| Northwood Space | ashby | 5 | `NorthwoodSpace` |
| ONE Finance | ashby | 3 | `oneapp` |
| Persona AI | ashby | 6 | `persona.ai` |
| Reliable Robotics | ashby | 5 | `reliable-robotics` |
| Revel | ashby | 7 | `revel` |
| Skyband Systems | ashby | 6 | `skyband systems` |
| Terranova | ashby | 5 | `terranova` |
| UiPath | ashby | 3 | `uipath` |
| Vital Lyfe | ashby | 3 | `vital-lyfe` |
| Zus Health | ashby | 4 | `zus-health` |
| AMCA | greenhouse | 3 | `amca` |
| Arc | greenhouse | 3 | `arcboatcompany` |
| Astera Labs | greenhouse | 18 | `asteraearlycareer2027` |
| Astronics | greenhouse | 4 | `astronicscorporation` |
| Atoms | greenhouse | 11 | `atoms` |
| Atoms | greenhouse | 11 | `cssmerge` |
| Audax Group | greenhouse | 3 | `audaxgroup` |
| Axon | greenhouse | 6 | `axontalentcommunity` |
| Bandwidth | greenhouse | 7 | `bandwidth` |
| C3.ai | greenhouse | 7 | `c3ascend` |
| CarGurus | greenhouse | 14 | `ecjobb` |
| Castelion | greenhouse | 3 | `castelioncorporation` |
| Compeer Financial | greenhouse | 8 | `compeerfinancial` |
| Crystal Dynamics | greenhouse | 3 | `crystaldynamics` |
| Dev Technology Group | greenhouse | 4 | `devtechnology` |
| Divergent Technologies | greenhouse | 3 | `divergent` |
| DriveWealth | greenhouse | 11 | `drivewealth` |
| DV Trading | greenhouse | 4 | `dvtrading` |
| Enova | greenhouse | 3 | `enova` |
| Esri | greenhouse | 5 | `studentprogram` |
| Farmers Mutual Hail | greenhouse | 6 | `farmersmutualhailinsurancecompany` |
| Flagship Pioneering | greenhouse | 8 | `fspco-op012325` |
| Freeform | greenhouse | 5 | `freeformfuturecorp` |
| Fussball Club Cincinnati LLC (“FC Cincinnati”) | greenhouse | 3 | `fccincinnati` |
| Gallup | greenhouse | 4 | `gallup` |
| GCM Grosvenor | greenhouse | 3 | `gcmgrosvenor` |
| General Matter | greenhouse | 3 | `generalmatter` |
| Hive Financial Systems | greenhouse | 5 | `hivefinancialsystems` |
| ID.me | greenhouse | 3 | `idmeuniversityrecruiting` |
| Inversion Space | greenhouse | 6 | `inversionspace` |
| K2 Space | greenhouse | 4 | `k2spacecorporation` |
| KnowBe4 | greenhouse | 3 | `knowbe4` |
| Lila Sciences | greenhouse | 5 | `lilasciences` |
| Muon Space | greenhouse | 9 | `muonspace` |
| National Information Solutions Cooperative | greenhouse | 19 | `nisc` |
| National Life | greenhouse | 5 | `nationallifeinsurancecompany` |
| Neros Technologies | greenhouse | 4 | `nerostechnologies` |
| Pacific Fusion | greenhouse | 3 | `pacificfusion` |
| ParetoHealth | greenhouse | 3 | `paretocaptiveservicesllc` |
| Perpay | greenhouse | 4 | `perpay` |
| Rendezvous Robotics | greenhouse | 3 | `rendezvousrobotics` |
| RF-SMART | greenhouse | 5 | `rfsmart` |
| Rocket Lab USA | greenhouse | 4 | `rocketlab` |
| Rugged Robotics | greenhouse | 3 | `ruggedrobotics` |
| Samsung Research America | greenhouse | 8 | `samsungresearchamericainternship` |
| Scout Space | greenhouse | 3 | `scoutspace` |
| SharkNinja | greenhouse | 9 | `sharkninjaoperatingllc` |
| SK hynix | greenhouse | 5 | `skhynixmemorysolutionsamericainc` |
| Stratolaunch | greenhouse | 3 | `stratolaunch` |
| The Allen Institute for AI | greenhouse | 4 | `thealleninstitute` |
| The Nuclear Company | greenhouse | 11 | `thenuclearcompany` |
| Toshiba Global Commerce Solutions | greenhouse | 7 | `toshibaglobalcommercesolutions` |
| TransMarket Group | greenhouse | 4 | `transmarketgroup` |
| Varda Space | greenhouse | 6 | `vardaspace` |
| Veeam Software | greenhouse | 7 | `veeamsoftware` |
| Analytic Partners | lever | 7 | `analyticpartners` |
| AnaVation | lever | 3 | `anavationllc` |
| CesiumAstro | lever | 13 | `CesiumAstro` |
| Commonwealth Fusion Systems | lever | 5 | `cfsenergy` |
| Exowatt | lever | 4 | `exowatt` |
| Field AI | lever | 5 | `field-ai` |
| Hermeus | lever | 4 | `hermeus` |
| Immuta | lever | 3 | `immuta` |
| Match Group | lever | 4 | `matchgroup` |
| Mom's Meals | lever | 3 | `momsmeals` |
| Pattern | lever | 6 | `pattern` |
| Pivotal Aero | lever | 3 | `pivotal` |
| Simbe Robotics | lever | 6 | `SimbeRobotics` |
| Stand Together | lever | 5 | `standtogether` |
| Toyota Research Institute | lever | 13 | `tri` |
| Booz Allen | workday | 86 | `bah/bah_jobs/wd1` |
| CACI | workday | 45 | `caci/external/wd1` |
| GE Vernova | workday | 49 | `gevernova/vernova_externalsite/wd5` |
| General Dynamics Information Technology | workday | 33 | `gdit/gdit_earlytalent/wd5` |
| General Motors | workday | 58 | `generalmotors/Careers_GM/wd5` |
| GlobalFoundries | workday | 44 | `globalfoundries/External/wd1` |
| Johnson & Johnson | workday | 40 | `jj/JJ/wd5` |
| Leidos | workday | 36 | `leidos/External/wd5` |
| Marvell | workday | 77 | `marvell/MarvellCareers/wd1` |
| Micron Technology | workday | 37 | `micron/External/wd1` |
| Northrop Grumman | workday | 73 | `ngc/Northrop_Grumman_External_Site/wd1` |
| RTX | workday | 304 | `globalhr/rec_rtx_ext_gateway/wd5` |
| T-Mobile | workday | 44 | `tmobile/External/wd1` |
| The Walt Disney Company | workday | 46 | `disney/disneycareerdc/wd5` |
| Xcel Energy | workday | 27 | `xcelenergy/External/wd1` |

Added **107 verified boards**: 92 Greenhouse/Lever/Ashby and 15 Workday. Added **33 company keywords**. Total Workday boards: **20 / 20**.

New TOP company keywords: `L3Harris Technologies`, `Qorvo`, `American Express`, `Nokia`, `Johns Hopkins Applied Physics Laboratory`, `Navy Federal`, `Boston Scientific`, `Intercontinental Exchange`, `General Dynamics Mission Systems`, `Shure`, `Keysight Technologies`, `Paccar`, `Vertiv`, `American Family Insurance Group`, `Garmin`, `Highmark Health`, `Hewlett Packard Enterprise`, `Philips`, `Renesas Electronics`, `Rockwell Automation`, `onsemi`, `Motorola`, `Nissan Global`, `The Toro Company`, `Applied Materials`, `The Federal Reserve System`, `NXP Semiconductors`, `Bose`, `Corning`, `KLA`, `Peraton`, `Ralliant`, `Sierra Nevada Corporation`.

## Considered and skipped

| Company / candidate | Reason |
|---|---|
| CALSTART (`lever:calstart`) | Verifier returned HTTP 404. |
| Cirrus Logic (`lever:cirrus`) | Verifier returned HTTP 404. |
| Meridian Partners (`greenhouse:morsecorpcoop`) | Greenhouse identifies the board as MORSE Corp Co-op Opportunities; company identity did not match the listing label. |
| NISC test board (`greenhouse:testnisc`) | Duplicate/test-named board; used the verified `nisc` board instead. |
| Klaviyo Campus (`greenhouse:klaviyocampus`) | Verifier succeeded but returned zero jobs; added the verified Ashby board derived from other Klaviyo listings. |
| Aurora Innovation (`ashby:aurora-operations-inc`) | Same board already configured as Aurora. |
| Riot Games (`greenhouse:riotgamesup`) | Verifier succeeded but returned zero jobs. |
| Ciena (`workday:ciena/CienaCareers/wd1`) | Workday verifier returned HTTP 422. |
| Disney general careers (`workday:disney/disneycareer/wd5`) | Verified but returned 6 jobs; selected Disney’s verified `disneycareerdc` site (88 jobs). |
| Workday: Hewlett Packard Enterprise, Rockwell Automation, Nissan Global, Applied Materials | Verified alternatives outside the top-15 Workday volume cutoff; retaining the highest-ranked 15 keeps the configured Workday list at its cap. |

## High-volume companies reachable only through feeds

These companies had at least 20 relevant listings in the feed window and no selected direct board. URL systems below show what the listings expose; “other” includes employer-specific career platforms.

| Company | Relevant postings / 120d | URL system(s) | Routing |
|---|---:|---|---|
| TikTok | 262 | other | TOP keyword / feed only |
| Tesla | 190 | other | TOP keyword / feed only |
| ByteDance | 112 | other | TOP keyword / feed only |
| AMD | 74 | other | TOP keyword / feed only |
| Amazon | 61 | other | TOP keyword / feed only |
| L3Harris Technologies | 60 | other | feed only |
| Qorvo | 53 | other | feed only |
| American Express | 47 | other | feed only |
| Nokia | 45 | other | feed only |
| Microsoft | 42 | other | TOP keyword / feed only |
| Johns Hopkins Applied Physics Laboratory | 39 | other | feed only |
| Navy Federal | 38 | other | feed only |
| Boston Scientific | 37 | other | feed only |
| Intercontinental Exchange | 34 | other | feed only |
| General Dynamics Mission Systems | 32 | other | feed only |
| Shure | 32 | other | feed only |
| Keysight Technologies | 31 | other | feed only |
| Paccar | 30 | other | feed only |
| Vertiv | 30 | other | feed only |
| American Family Insurance Group | 26 | workday/other | feed only |
| Garmin | 26 | other | feed only |
| Highmark Health | 26 | workday/other | feed only |
| Visa | 25 | workday/other | TOP keyword / feed only |
| Hewlett Packard Enterprise | 24 | other/workday | feed only |
| Philips | 24 | workday/other | feed only |
| Renesas Electronics | 24 | other | feed only |
| Rockwell Automation | 24 | workday/other | feed only |
| onsemi | 23 | other | TOP keyword / feed only |
| Cisco | 22 | other | TOP keyword / feed only |
| Motorola | 22 | workday/other | feed only |
| Nissan Global | 22 | workday | feed only |
| The Toro Company | 22 | workday/other | feed only |
| Applied Materials | 21 | workday/other | feed only |
| The Federal Reserve System | 21 | workday/other | feed only |
| NXP Semiconductors | 20 | workday | feed only |

Large own-career-site companies already covered by exact company keywords and aggregate feeds include Google, Amazon, Tesla, TikTok, ByteDance, Qualcomm, AMD, and Microsoft.
