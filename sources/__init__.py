from .synmerco import fetch_synmerco_deals
from .moltjobs import fetch_moltjobs_deals
from .hyrve import fetch_hyrve_deals
from .superteam import fetch_superteam_deals
from .makefun import fetch_makefun_deals
from .github_bounties import fetch_github_bounties
from .topcoder import fetch_topcoder_deals
from .devpost import fetch_devpost_deals

ALL_FETCHERS = [
    ("Synmerco", fetch_synmerco_deals),
    ("MoltJobs", fetch_moltjobs_deals),
    ("HYRVE", fetch_hyrve_deals),
    ("Superteam Earn", fetch_superteam_deals),
    ("make.fun", fetch_makefun_deals),
    ("GitHub Bounties", fetch_github_bounties),
    ("Topcoder", fetch_topcoder_deals),
    ("Devpost", fetch_devpost_deals),
]