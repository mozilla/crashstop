# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla
from libmozdata.patchanalysis import get_patch_info
from . import utils
from .logger import logger


def get_bz_params(start_date, end_date):
    fields = ['id', 'cf_crash_signature']
    regexp = 'http[s]?://hg\.mozilla\.org/(releases/)?mozilla-[^/]+/rev/[0-9a-f]+' # NOQA
    params = {'include_fields': fields,
              'f1': 'cf_crash_signature',
              'o1': 'isnotempty',
              'f2': 'longdesc',
              'o2': 'regexp',
              'v2': regexp,
              'f3': 'longdesc',
              'o3': 'changedafter',
              'v3': start_date,
              'f4': 'longdesc',
              'o4': 'changedbefore',
              'v4': end_date}

    return params


def get_bugs(start_date, end_date):
    logger.info('Get bugs from {} to {}: started.'.format(start_date,
                                                          end_date))

    # the search query can be long to evaluate
    TIMEOUT = 240

    def bug_handler(bug, data):
        if 'cf_crash_signature' in bug:
            sgns = bug['cf_crash_signature']
            sgns = utils.get_signatures([sgns])
            data[str(bug['id'])] = sgns

    bugs = {}
    Bugzilla(get_bz_params(start_date, end_date),
             bughandler=bug_handler,
             bugdata=bugs,
             timeout=TIMEOUT).get_data().wait()

    res = {}
    for bugid, sgns in bugs.items():
        for sgn in sgns:
            if sgn not in res:
                res[sgn] = []
            res[sgn].append(bugid)

    logger.info('{} bugs and {} signatures collected.'.format(len(bugs),
                                                              len(res)))

    return res, list(bugs.keys())


def filter_land(land, date_ranges):
    res = {}
    if land:
        for chan, pushdate in land.items():
            md, Md = date_ranges[chan]
            if md <= pushdate:
                res[chan] = pushdate
    return res


def get(start_date, end_date, date_ranges):
    sgns, bugs = get_bugs(start_date, end_date)
    channels = utils.get_channels()

    logger.info('Get patch info for {} bugs: started.'.format(len(bugs)))
    patches = get_patch_info(bugs, channels=channels)
    logger.info('{} bugs have patches.'.format(len(patches)))

    pushdates = {}
    for sgn, bugs in sgns.items():
        for bug in bugs:
            land = patches.get(bug, {}).get('land')
            land = filter_land(land, date_ranges)
            if land:
                if sgn in pushdates:
                    pushdates[sgn][bug] = land
                else:
                    pushdates[sgn] = {bug: land}

    logger.info('{} signatures have patches.'.format(len(pushdates)))
    logger.info('Get patch info: finished.')

    return pushdates
