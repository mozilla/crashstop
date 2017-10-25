# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import copy
from collections import defaultdict
from dateutil.relativedelta import relativedelta
import functools
from libmozdata import socorro, utils as lmdutils
from libmozdata.patchanalysis import get_patch_info
from . import config
from . import utils


def remove_dup_versions(data):
    res = {}
    if 'nightly' in data:
        res['nightly'] = [(b, v) for b, v, _ in data['nightly']]

    for chan in ['beta', 'release']:
        if chan in data:
            versions = {}
            for b, v, c in data[chan]:
                if v in versions:
                    if c > versions[v][1]:
                        versions[v] = (b, c)
                else:
                    versions[v] = (b, c)
            res[chan] = []
            for v, i in versions.items():
                bid, _ = i
                res[chan].append((bid, v))
    return res


def get_buildids(search_date, channels, product):
    data = {chan: list() for chan in channels}

    def handler(threshold, json, data):
        if json['errors'] or not json['facets']['build_id']:
            return
        for facets in json['facets']['build_id']:
            count = facets['count']
            if count > threshold:
                version = facets['facets']['version'][0]['term']
                buildid = facets['term']
                data.append((buildid, version, count))

    params = {'product': product,
              'release_channel': '',
              'date': search_date,
              '_aggs.build_id': 'version',
              '_results_number': 0,
              '_facets_size': 1000}

    searches = []
    for chan in channels:
        params = copy.deepcopy(params)
        params['release_channel'] = chan
        threshold = config.get_min_total(product, chan)
        hdler = functools.partial(handler, threshold)
        searches.append(socorro.SuperSearch(params=params,
                                            handler=hdler,
                                            handlerdata=data[chan]))

    for s in searches:
        s.wait()

    data = remove_dup_versions(data)

    res = {}
    for chan, bids in data.items():
        bids = sorted(bids, reverse=True)
        min_v = config.get_versions(product, chan)
        if len(bids) > min_v:
            bids = bids[:min_v]
        bids = [(utils.get_build_date(bid), v) for bid, v in bids]
        res[chan] = bids

    return res


def get_sgns_by_buildid(channels, product='Firefox',
                        date='today', query={}):
    today = lmdutils.get_date_ymd(date)
    few_days_ago = today - relativedelta(days=config.get_limit())
    search_date = socorro.SuperSearch.get_search_date(few_days_ago)
    bids = get_buildids(search_date, channels, product)
    base = {chan: {bid: 0 for bid, _ in bids[chan]} for chan in channels}
    data = {}

    def handler(base, chan, bid, json, data):
        if json['errors'] or not json['facets']['signature']:
            return
        for facets in json['facets']['signature']:
            sgn = facets['term']
            if sgn not in data:
                data[sgn] = copy.deepcopy(base)
            data[sgn][bid] = facets['count']

    base_params = {'product': product,
                   'release_channel': '',
                   'build_id': '',
                   'date': search_date,
                   '_aggs.signature': 'release_channel',
                   '_results_number': 0,
                   '_facets_size': 10000}
    base_params.update(query)

    searches = []
    for chan in channels:
        params = copy.deepcopy(base_params)
        params['release_channel'] = chan
        data[chan] = {}
        for bid, _ in bids[chan]:
            params = copy.deepcopy(params)
            params['build_id'] = utils.get_buildid(bid)
            hdler = functools.partial(handler, base[chan], chan, bid)
            searches.append(socorro.SuperSearch(params=params,
                                                handler=hdler,
                                                handlerdata=data[chan]))

    for s in searches:
        s.wait()

    res = defaultdict(lambda: dict())
    for chan, i in data.items():
        threshold = config.get_min(product, chan)
        for sgn, j in i.items():
            if max(j.values()) >= threshold:
                res[chan][sgn] = j

    return res, bids


def compare_lands(l1, l2):
    chans = utils.get_channels()
    for chan in chans:
        if chan in l1 and chan in l2:
            if l1[chan] <= l2[chan]:
                return l2
    return None


def get_patches(signatures):
    bugs_by_signature = socorro.Bugs.get_bugs(list(signatures))
    bugs = set()
    for b in bugs_by_signature.values():
        bugs = bugs.union(set(b))

    patches = get_patch_info(bugs, channels=utils.get_channels())
    pushdates = {}

    for sgn, bugs in bugs_by_signature.items():
        for bug in map(str, bugs):
            land = patches.get(bug, {}).get('land', {})
            if land:
                if sgn in pushdates:
                    land = compare_lands(pushdates[sgn]['land'], land)
                    if land:
                        pushdates[sgn]['land'] = land
                        pushdates[sgn]['bugid'] = bug
                else:
                    pushdates[sgn] = {'land': land,
                                      'bugid': bug}
    return pushdates
