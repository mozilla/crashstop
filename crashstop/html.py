# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from flask import request, render_template
import json
from . import utils, models, signatures, cache


def sgns():
    product = request.args.get('product', '')
    product = utils.get_correct_product(product)
    channel = request.args.get('channel', '')
    channel = utils.get_correct_channel(channel)
    filt = request.args.get('filter', 'all')
    filt = utils.get_correct_filter(filt)

    data = models.Signatures.get_bypc(product, channel, filt)
    signatures.prepare_signatures_for_html(data, product, channel)

    return render_template('signatures.html',
                           product=product,
                           products=utils.get_products(),
                           channel=channel,
                           channels=utils.get_channels(),
                           data=data,
                           filt=filt,
                           enumerate=enumerate)


def bug():
    bugid = request.args.get('id', '')
    bugid = utils.get_bug_number(bugid)
    data = models.Signatures.get_bybugid(bugid)
    data, links, versions, _, _ = signatures.prepare_bug_for_html(data)

    return render_template('bug.html',
                           data=data,
                           links=links,
                           bugid=bugid,
                           versions=versions,
                           enumerate=enumerate)


def crashdata():
    sgns = request.args.getlist('signatures')
    hgurls = request.args.getlist('hgurls')
    products = request.args.getlist('products')
    products = utils.get_correct_products(products)
    data = signatures.get_for_urls_sgns(hgurls, sgns, products)
    data, links, versions, _, _ = signatures.prepare_bug_for_html(data)

    return render_template('crashdata.html',
                           data=data,
                           links=links,
                           versions=versions,
                           products=utils.get_products(),
                           enumerate=enumerate)


def sumup():
    # cache.clear()
    sgns = request.args.getlist('s')
    hgurls = request.args.getlist('h')
    addon_version = request.args.get('v', '')
    extra = dict(request.args)
    for x in 'shv':
        if x in extra:
            del extra[x]

    data, links, versions, affected, has_extra = cache.get_sumup(hgurls, sgns, extra)
    return render_template('sumup.html',
                           data=data,
                           links=links,
                           versions=versions,
                           affected=affected,
                           has_extra=has_extra,
                           products=utils.get_products(),
                           addon_version=addon_version,
                           enumerate=enumerate,
                           zip=zip,
                           jsonify=json.dumps)
