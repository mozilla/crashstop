# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import OrderedDict
from libmozdata import socorro
from . import datacollector as dc
from . import utils


def get_min_max_dates(numbers):
    dates = sorted(numbers.keys())
    return dates[0], dates[-1]


def get_interesting_sgns(data, patches, chan):
    res = {}
    for sgn, numbers in data.items():
        md, Md = get_min_max_dates(numbers)
        if sgn in patches and chan in patches[sgn]['land']:
            pushdate = patches[sgn]['land'][chan]
            if md <= pushdate <= Md:
                res[sgn] = {'numbers': numbers,
                            'pushdate': pushdate,
                            'bugid': int(patches[sgn]['bugid'])}
    return res


def get(date='today'):
    signatures = set()
    patches = None
    products = utils.get_products()
    channels = utils.get_channels()
    res_byprod = {}
    bids_byprod = {}
    for product in products:
        data, bids = dc.get_sgns_by_buildid(channels,
                                            product=product,
                                            date=date)
        res_byprod[product] = data
        bids_byprod[product] = {k: dict(v) for k, v in bids.items()}
        for info in data.values():
            signatures |= set(info.keys())

    if signatures:
        patches = dc.get_patches(signatures)

    res = {prod: {chan: {} for chan in channels} for prod in products}
    for prod, i in res_byprod.items():
        for chan, data in i.items():
            res[prod][chan] = get_interesting_sgns(data, patches, chan)

    return res, bids_byprod


def get_for_urls_sgns(hg_urls, signatures, products, date='today'):
    from .models import Buildid

    data = {}
    res = {'data': data,
           'versions': {}}

    signatures = utils.get_signatures(signatures)
    if not signatures:
        return res

    chan_rev = utils.analyze_hg_urls(hg_urls)
    if not chan_rev:
        return res

    towait, pushdates = dc.get_pushdates(chan_rev)

    products = utils.get_products() if not products else products
    bids = {}
    res['versions'] = versions = {}
    dates = {}
    for product in products:
        bids[product] = d1 = {}
        for chan in chan_rev.keys():
            pc = Buildid.get_pc(product, chan)
            v = Buildid.get_versions(pc)
            versions[(product, chan)] = v
            dates[(product, chan)] = d1[chan] = sorted(v.keys())

    sgns_data = dc.get_sgns_data(chan_rev.keys(), bids,
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
            pushdate = pushdates[chan]
            ds = dates[(product, chan)]
            for sgn, numbers in j.items():
                raw = [0] * len(ds)
                installs = [0] * len(ds)
                for k, d in enumerate(ds):
                    n = numbers[d]
                    raw[k] = n['raw']
                    installs[k] = n['installs']
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
