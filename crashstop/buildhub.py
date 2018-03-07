# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import requests
import time
from . import config, datacollector as dc, utils
from .logger import logger


URL = 'https://buildhub.prod.mozaws.net/v1/buckets/build-hub/collections/releases/search'
VERSION_PAT = '[0-9\.]+(([ab][0-9]+)|esr)?'
CHANNELS = ['nightly', 'aurora', 'beta', 'release', 'esr']
PRODUCTS = ['firefox', 'devedition', 'fennec']
RPRODS = {'firefox': 'Firefox',
          'devedition': 'Firefox',
          'fennec': 'FennecAndroid'}


def make_request(params, sleep, retry, callback):
    """Query Buildhub"""
    params = json.dumps(params)

    for _ in range(retry):
        r = requests.post(URL, data=params)
        if 'Backoff' in r.headers:
            time.sleep(sleep)
        else:
            try:
                return callback(r.json())
            except BaseException as e:
                logger.error('Buildhub query failed with parameters: {}.'.format(params))
                logger.error(e, exc_info=True)
                return None

    logger.error('Too many attempts in buildhub.make_request (retry={})'.format(retry))

    return None


def get_info(data):
    """Get build info from Buildhub data"""
    res = {}
    aggs = data['aggregations']
    buildids = {}
    buildids_per_prod = {}

    for product in aggs['products']['buckets']:
        prod = RPRODS[product['key']]
        if prod in res:
            res_p = res[prod]
        else:
            res[prod] = res_p = {}
        if prod in buildids_per_prod:
            buildids_p = buildids_per_prod[prod]
        else:
            buildids_per_prod[prod] = buildids_p = {}

        for channel in product['channels']['buckets']:
            chan = channel['key']
            if chan in res_p:
                res_pc = res_p[chan]
            elif chan != 'aurora':
                res_p[chan] = res_pc = set()

            for buildid in channel['buildids']['buckets']:
                bid = utils.get_build_date(buildid['key'])
                version = buildid['versions']['buckets'][0]['key']
                b = None
                if chan == 'aurora':
                    if version.endswith('b1') or version.endswith('b2'):
                        b = bid
                        res_p['beta'].add((bid, version))
                else:
                    b = bid
                    res_pc.add((bid, version))

                if b not in buildids:
                    buildids[b] = True
                else:
                    buildids[b] = False
                if b not in buildids_p:
                    buildids_p[b] = True
                else:
                    buildids_p[b] = False

    for v1 in res.values():
        for chan, v2 in v1.items():
            v1[chan] = list(sorted(v2))

    dc.filter_nightly_buildids(res)

    for prod, v1 in res.items():
        buildids_p = buildids_per_prod[prod]
        for chan, v2 in v1.items():
            min_v = config.get_versions(prod, chan)
            if len(v2) > min_v:
                v2 = v2[-min_v:]
            v1[chan] = [(b, v, buildids[b], buildids_p[b]) for b, v in v2]

    return res


def get():
    """Get buildids and versions info from Buildhub"""
    data = {
        'aggs': {
            'products': {
                'terms': {
                    'field': 'source.product',
                    'size': len(PRODUCTS)
                },
                'aggs': {
                    'channels': {
                        'terms': {
                            'field': 'target.channel',
                            'size': len(CHANNELS)
                        },
                        'aggs': {
                            'buildids': {
                                'terms': {
                                    'field': 'build.id',
                                    'size': 200,
                                    'order': {
                                        '_term': 'desc'
                                    }
                                },
                                'aggs': {
                                    'versions': {
                                        'terms': {
                                            'field': 'target.version',
                                            'size': 1,
                                            'order': {
                                                '_term': 'desc'
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        'query': {
            'bool': {
                'filter': [
                    {'regexp': {'target.version': {'value': VERSION_PAT}}},
                    {'terms': {'target.channel': CHANNELS}},
                    {'terms': {'source.product': PRODUCTS}}
                ]
            }
        },
        'size': 0}

    return make_request(data, 1, 100, get_info)
