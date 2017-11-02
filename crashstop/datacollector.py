# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import copy
from datetime import datetime
from dateutil.relativedelta import relativedelta
import functools
from libmozdata import socorro, utils as lmdutils
from libmozdata.connection import Query
from libmozdata.hgmozilla import Revision
from . import config, utils, tools
from .const import RAW, INSTALLS
from .logger import logger


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


def get_buildids(search_date, channels, products):
    data = {p: {c: list() for c in channels} for p in products}

    def handler(chan, threshold, json, data):
        if json['errors'] or not json['facets']['build_id']:
            return
        for facets in json['facets']['build_id']:
            count = facets['count']
            if count >= threshold:
                version = facets['facets']['version'][0]['term']
                if chan != 'beta' or not version.endswith('a2'):
                    buildid = facets['term']
                    data.append((buildid, version, count))

    params = {'product': '',
              'release_channel': '',
              'date': search_date,
              '_aggs.build_id': 'version',
              '_results_number': 0,
              '_facets_size': 1000}

    queries = []
    for prod in products:
        pparams = copy.deepcopy(params)
        pparams['product'] = prod
        for chan in channels:
            params = copy.deepcopy(pparams)
            if chan == 'beta' and prod == 'Firefox':
                params['release_channel'] = ['beta', 'aurora']
            else:
                params['release_channel'] = chan
            threshold = config.get_min_total(prod, chan)
            hdler = functools.partial(handler, chan, threshold)
            queries.append(Query(socorro.SuperSearch.URL,
                                 params=params,
                                 handler=hdler,
                                 handlerdata=data[prod][chan]))

    socorro.SuperSearch(queries=queries).wait()

    for prod, info in data.items():
        data[prod] = remove_dup_versions(info)

    res = {}
    for prod, info in data.items():
        res[prod] = d = {}
        for chan, bids in info.items():
            bids = sorted(bids)
            min_v = config.get_versions(prod, chan)
            if len(bids) > min_v:
                bids = bids[-min_v:]
            bids = [(utils.get_build_date(bid), v) for bid, v in bids]
            d[chan] = bids

    logger.info('Buildids for {}/{} got.'.format(products, channels))

    return res


def get_sgns_by_buildid(signatures, channels, products, search_date, bids):
    base = utils.get_base_list(bids)
    limit = config.get_limit_facets()

    logger.info('Get crash numbers for {}-{}: started.'.format(products,
                                                               channels))

    def handler(base, index, json, data):
        if json['errors'] or not json['facets']['signature']:
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
            params = copy.deepcopy(pparams)
            params['release_channel'] = chan
            data = {}
            sbids = [b for b, _ in bids_prod[chan]]
            for index, bid in enumerate(sbids):
                queries = []
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


def get_sgns_data(channels, bids, signatures, products, date='today'):
    today = lmdutils.get_date_ymd(date)
    few_days_ago = today - relativedelta(days=config.get_limit())
    search_date = socorro.SuperSearch.get_search_date(few_days_ago)

    nbase = [0, 0]
    data = {}

    for product in products:
        data[product] = d1 = {}
        b1 = bids[product]
        for chan in channels:
            d1[chan] = d2 = {}
            b2 = b1[chan]
            for signature in signatures:
                d2[signature] = {bid: nbase.copy() for bid in b2}

    limit = 100
    signatures = ['=' + s for s in signatures]

    def handler(bid, json, data):
        if json['errors'] or not json['facets']['signature']:
            return
        for facets in json['facets']['signature']:
            sgn = facets['term']
            data[sgn][bid][RAW] = facets['count']
            facets = facets['facets']
            n = len(facets['install_time'])
            if n == limit:
                n = facets['cardinality_install_time']['value']
            data[sgn][bid][INSTALLS] = n

    base_params = {'product': '',
                   'release_channel': '',
                   'build_id': '',
                   'signature': signatures,
                   'date': search_date,
                   '_aggs.signature': ['install_time',
                                       '_cardinality.install_time'],
                   '_results_number': 0,
                   '_facets': 'release_channel',
                   '_facets_size': limit}

    queries = []
    for product in products:
        pparams = copy.deepcopy(base_params)
        pparams['product'] = product
        d1 = data[product]
        b1 = bids[product]
        for chan in channels:
            params = copy.deepcopy(pparams)
            params['release_channel'] = chan
            d2 = d1[chan]
            for bid in b1[chan]:
                params = copy.deepcopy(params)
                params['build_id'] = utils.get_buildid(bid)
                hdler = functools.partial(handler, bid)
                queries.append(Query(socorro.SuperSearch.URL,
                                     params=params,
                                     handler=hdler,
                                     handlerdata=d2))
    socorro.SuperSearch(queries=queries).wait()

    return data


def get_pushdates(chan_rev):

    def handler(json, data):
        pushdate = json['pushdate'][0]
        pushdate = lmdutils.as_utc(datetime.utcfromtimestamp(pushdate))
        data.append(pushdate)

    res = []
    data = {}

    for chan, revs in chan_rev.items():
        data[chan] = pd = []
        for rev in revs:
            res.append(Revision(channel=chan,
                                params={'node': rev},
                                handler=handler,
                                handlerdata=pd))

    return res, data
