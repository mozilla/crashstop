# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import OrderedDict
from dateutil.relativedelta import relativedelta
from libmozdata import socorro
from libmozdata import utils as lmdutils
from . import datacollector as dc
from . import utils, tools, config, patchinfo
from .const import RAW, INSTALLS


def get(date='today',
        products=utils.get_products(),
        channels=utils.get_channels()):
    today = lmdutils.get_date_ymd(date)
    few_days_ago = today - relativedelta(days=config.get_limit())
    search_date = socorro.SuperSearch.get_search_date(few_days_ago)

    bids = dc.get_buildids(search_date, channels, products)
    start_date, end_date, date_ranges = utils.get_dates(bids)
    patches = patchinfo.get(start_date, end_date, date_ranges)

    signatures = set(patches.keys())
    res, ratios = dc.get_sgns_by_buildid(signatures, channels,
                                         products, search_date,
                                         bids)
    res = tools.compute_success(res, patches, bids, ratios)

    return res, bids, ratios


def get_for_urls_sgns(hg_urls, signatures, products, date='today'):
    from .models import Buildid

    data = {}
    res = {'data': data,
           'versions': {}}

    signatures = utils.get_signatures(signatures)
    if not signatures:
        return res

    chan_rev = utils.analyze_hg_urls(hg_urls)
    towait, pushdates = dc.get_pushdates(chan_rev)

    products = utils.get_products() if not products else products
    bids = {}
    res['versions'] = versions = {}
    dates = {}
    channels = chan_rev.keys() if chan_rev else utils.get_channels()
    for product in products:
        bids[product] = d1 = {}
        for chan in channels:
            pc = Buildid.get_pc(product, chan)
            v = Buildid.get_versions(pc)
            versions[(product, chan)] = v
            dates[(product, chan)] = d1[chan] = sorted(v.keys())

    sgns_data = dc.get_sgns_data(channels, bids,
                                 signatures, products,
                                 date=date)

    for tw in towait:
        tw.wait()

    for chan, pds in pushdates.items():
        pushdates[chan] = max(pds)

    for product, i in sgns_data.items():
        data[product] = d1 = {}
        for chan, j in i.items():
            d1[chan] = d2 = {}
            pushdate = pushdates.get(chan)
            ds = dates[(product, chan)]
            for sgn, numbers in j.items():
                raw = [0] * len(ds)
                installs = [0] * len(ds)
                for k, d in enumerate(ds):
                    n = numbers[d]
                    raw[k] = n[RAW]
                    installs[k] = n[INSTALLS]
                d2[sgn] = {'pushdate': pushdate,
                           'dates': ds,
                           'raw': raw,
                           'installs': installs}

    return res


def prepare_signatures_for_html(data, product, channel):
    if channel == 'beta' and product == 'Firefox':
        c = ['beta', 'aurora']
    else:
        c = channel
    params = utils.get_params_for_link(query={'release_channel': c,
                                              'product': product})
    versions = data['versions']
    dates = sorted(versions.keys())
    data['buildids'] = buildids = [utils.get_buildid(d) for d in dates]
    data['versions'] = {utils.get_buildid(d): v for d, v in versions.items()}
    links = {}

    for sgn, info in data['signatures'].items():
        sgn = utils.get_str(sgn)
        params['signature'] = utils.get_esearch_sgn(sgn)
        url = socorro.SuperSearch.get_link(params)
        url += '#facet-build_id'
        info['socorro_url'] = url
        for bid in buildids:
            params['build_id'] = '=' + bid
            url = socorro.SuperSearch.get_link(params)
            url += '#crash-reports'
            links[(sgn, bid)] = url
        del params['build_id']

    for info in data['signatures'].values():
        utils.set_position(info, dates)

    data['signatures'] = sorted(data['signatures'].items(),
                                key=lambda p: (p[1]['bugid'], p[0]),
                                reverse=True)

    data['links'] = links

    return data


def prepare_bug_for_html(data):
    params = utils.get_params_for_link()
    links = {}
    versions = data['versions']
    data = data['data']

    for k, v in versions.items():
        versions[k] = {utils.get_buildid(d): ver for d, ver in v.items()}

    for prod, i in data.items():
        params['product'] = prod
        for chan, j in i.items():
            c = ['beta', 'aurora'] if chan == 'beta' else chan
            params['release_channel'] = c
            for sgn, info in j.items():
                params['signature'] = utils.get_esearch_sgn(sgn)
                url = socorro.SuperSearch.get_link(params)
                url += '#facet-build_id'
                info['socorro_url'] = url
                dates = info['dates']
                del info['dates']
                utils.set_position(info, dates)
                info['buildids'] = bids = []
                for d in dates:
                    bid = utils.get_buildid(d)
                    bids.append(bid)
                    params['build_id'] = '=' + bid
                    url = socorro.SuperSearch.get_link(params)
                    url += '#crash-reports'
                    links[(sgn, bid)] = url
                if 'build_id' in params:
                    del params['build_id']

    # order the data
    results = OrderedDict()
    for prod in utils.get_products():
        if prod in data:
            results[prod] = d = OrderedDict()
            for chan in utils.get_channels():
                if chan in data[prod]:
                    d[chan] = sorted(data[prod][chan].items())

    return results, links, versions
