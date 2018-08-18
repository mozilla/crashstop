# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict
import copy
from datetime import datetime
from dateutil.relativedelta import relativedelta
import functools
from libmozdata import socorro, utils as lmdutils
from libmozdata.connection import Query, Connection
from libmozdata.hgmozilla import Revision
from . import config, utils, tools
from .const import RAW, INSTALLS, PLATFORMS, STARTUP
from .logger import logger


def filter_nightly_buildids(buildids):

    def handler(threshold, json, data):
        if not json['facets']['build_id']:
            return
        for facets in json['facets']['build_id']:
            count = facets['count']
            if count >= threshold:
                data[str(facets['term'])] = True

    params = {'product': '',
              'build_id': '',
              'date': '',
              'release_channel': 'nightly',
              '_aggs.build_id': 'release_channel',
              '_results_number': 0,
              '_facets': 'release_channel',
              '_facets_size': 1000}

    data = {'Firefox': None,
            'FennecAndroid': None}
    queries = []
    for prod in data.keys():
        pparams = copy.deepcopy(params)
        pparams['product'] = prod
        threshold = config.get_min_total(prod, 'nightly')
        data[prod] = data_prod = {}
        for bids in Connection.chunks(buildids[prod]['nightly'], chunk_size=64):
            pparams = copy.deepcopy(pparams)
            pparams['date'] = '>=' + utils.get_build_date(bids[0][0]).strftime('%Y-%m-%d')
            pparams['build_id'] = L = []
            for b in bids:
                L.append(b[0])
                data_prod[b[0]] = False

            hdler = functools.partial(handler, threshold)
            queries.append(Query(socorro.SuperSearch.URL,
                                 params=pparams,
                                 handler=hdler,
                                 handlerdata=data_prod))

    socorro.SuperSearch(queries=queries).wait()

    for prod, info in data.items():
        bids = buildids[prod]['nightly']
        L = [(bid, info[bid[0]]) for bid in bids]
        for i in range(len(L) - 1, -1, -1):
            if not L[i][1]:
                L[i] = (L[i][0], True)
            else:
                break
        buildids[prod]['nightly'] = [x[0] for x in L if x[1]]


def get_sgns_by_buildid(signatures, channels, products, search_date, bids):
    base = utils.get_base_list(bids)
    limit = config.get_limit_facets()

    logger.info('Get crash numbers for {}-{}: started.'.format(products,
                                                               channels))

    def handler(base, index, json, data):
        if not json['facets']['signature']:
            return
        for facets in json['facets']['signature']:
            sgn = facets['term']
            if sgn not in data:
                data[sgn] = copy.deepcopy(base)
            data[sgn][index][RAW] = facets['count']
            facets = facets['facets']
            n = len(facets['install_time'])
            if n == limit:
                n = facets['cardinality_install_time']['value']
            data[sgn][index][INSTALLS] = n

    base_params = {'product': '',
                   'release_channel': '',
                   'build_id': '',
                   'date': search_date,
                   '_aggs.signature': ['install_time',
                                       '_cardinality.install_time'],
                   '_results_number': 0,
                   '_facets': 'release_channel',
                   '_facets_size': limit}

    ratios = {}
    res = {}

    for prod in products:
        pparams = copy.deepcopy(base_params)
        pparams['product'] = prod
        base_prod = base[prod]
        bids_prod = bids[prod]
        ratios[prod] = ratios_prod = {}
        res[prod] = res_prod = {}
        for chan in channels:
            if chan not in bids_prod:
                continue

            params = copy.deepcopy(pparams)
            params['release_channel'] = chan
            data = {}
            sbids = [b[0] for b in bids_prod[chan]]
            queries = []
            for index, bid in enumerate(sbids):
                params = copy.deepcopy(params)
                params['build_id'] = utils.get_buildid(bid)
                hdler = functools.partial(handler, base_prod[chan], index)
                queries.append(Query(socorro.SuperSearch.URL,
                                     params=params,
                                     handler=hdler,
                                     handlerdata=data))
            socorro.SuperSearch(queries=queries).wait()
            ratios_prod[chan] = tools.get_global_ratios(data)

            # now we've ratios, we can remove useless signatures
            res_prod[chan] = {s: n for s, n in data.items() if s in signatures}

    logger.info('Get crash numbers for {}-{}: finished.'.format(products,
                                                                channels))
    return res, ratios


def analyze_uptime(histo):
    res = {}
    for h in histo:
        term = h['term']
        if term > 60:
            break
        for i in h['facets']['build_id']:
            bid = i['term']
            count = i['count']
            if bid in res:
                res[bid] += count
            else:
                res[bid] = count
    return res


def get_sgns_data_helper(data, signatures, bids, nbase, extra, search_date, product=None, channel=None):
    limit = 80

    def handler(sgn, bids, nbase, json, data):
        if not json['facets']['build_id']:
            return
        for facets in json['facets']['build_id']:
            rawbid = facets['term']
            bid = utils.get_build_date(rawbid)
            prod, chan = bids[bid]
            dpc = data[prod][chan]
            nums = dpc[sgn]
            if isinstance(nums, list):
                dpc[sgn] = nums = {b: copy.copy(nbase) for b in dpc[sgn]}
            if bid in nums:
                n = nums[bid]
                n[RAW] = facets['count']
                facets = facets['facets']
                N = len(facets['install_time'])
                if N == limit:
                    N = facets['cardinality_install_time']['value']
                n[INSTALLS] = N
                n[STARTUP] = utils.startup_crash_rate(facets['startup_crash'])
                n[PLATFORMS] = utils.analyze_platforms(facets['platform_pretty_version'])

    base_params = {'build_id': [utils.get_buildid(bid) for bid in bids.keys()],
                   'signature': '',
                   'date': search_date,
                   '_aggs.build_id': ['install_time',
                                      '_cardinality.install_time',
                                      'startup_crash',
                                      'platform_pretty_version'],
                   '_results_number': 0,
                   '_facets': 'signature',
                   '_facets_size': limit}

    if product:
        base_params['product'] = product
    if channel:
        base_params['release_channel'] = ['beta', 'aurora'] if channel == 'beta' else channel

    utils.update_params(base_params, extra)

    queries = []

    for signature in signatures:
        params = copy.deepcopy(base_params)
        params['signature'] = '=' + signature
        hdler = functools.partial(handler, signature, bids, nbase)
        queries.append(Query(socorro.SuperSearch.URL,
                             params=params,
                             handler=hdler,
                             handlerdata=data))

    res = socorro.SuperSearch(queries=queries)
    return res


def get_sgns_data(channels, versions, signatures, extra, products, towait, date='today'):
    today = lmdutils.get_date_ymd(date)
    few_days_ago = today - relativedelta(days=config.get_limit())
    search_date = socorro.SuperSearch.get_search_date(few_days_ago)
    nbase = [0, 0, 0, {}]
    data = {}
    unique = {}
    unique_prod = defaultdict(lambda: dict())
    leftovers = {}
    allbids = {}

    for p, i in versions.items():
        allbids[p] = allbids_p = {}
        for c, j in i.items():
            allbids_p[c] = allbids_pc = []
            for b, k in j.items():
                allbids_pc.append(b)
                v, u, up = k
                if u:
                    unique[b] = (p, c)
                elif up:
                    unique_prod[p][b] = (p, c)
                else:
                    leftovers[b] = (p, c)

    for product in products:
        data[product] = d1 = {}
        b1 = allbids[product]
        for chan in channels:
            d1[chan] = d2 = {}
            b2 = b1[chan]
            for signature in signatures:
                d2[signature] = b2

    if not unique_prod:
        # if we've only unique buildids: only N queries for the N signatures
        towait.append(get_sgns_data_helper(data, signatures, unique,
                                           nbase, extra, search_date))
    else:
        # if a buildid is unique then it's unique for its product too.
        # So we've only 2xN queries (2 == len(['Firefox', 'FennecAndroid']))
        for b, x in unique.items():
            p, c = x
            unique_prod[p][b] = (p, c)
        for prod, bids in unique_prod.items():
            towait.append(get_sgns_data_helper(data, signatures, bids,
                                               nbase, extra, search_date,
                                               product=prod))

    # handle the leftovers: normally they should be pretty rare
    # we've them when they're not unique within the same product (e.g. a nightly and a beta have the same buildid)
    for b, x in leftovers.items():
        prod, chan = x
        towait.append(get_sgns_data_helper(data, signatures, leftovers,
                                           nbase, extra, search_date,
                                           product=prod, channel=chan))

    return data


def get_pushdates(chan_rev):

    def handler(json, data):
        if not json['backedoutby']:
            pushdate = json['pushdate'][0]
            pushdate = lmdutils.as_utc(datetime.utcfromtimestamp(pushdate))
            data.append(pushdate)

    res = []
    data = {}

    for chan, revs in chan_rev.items():
        if chan.startswith('esr'):
            if 'esr' not in data:
                data['esr'] = pd = []
            else:
                pd = data['esr']
        else:
            data[chan] = pd = []

        for rev in revs:
            res.append(Revision(channel=chan,
                                params={'node': rev},
                                handler=handler,
                                handlerdata=pd))

    return res, data
