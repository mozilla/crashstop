# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from flask import request, render_template
from . import utils, models, signatures


def sgns():
    product = request.args.get('product', '')
    product = utils.get_correct_product(product)
    channel = request.args.get('channel', '')
    channel = utils.get_correct_channel(channel)

    data = models.Signatures.get_bypc(product, channel)
    signatures.prepare_for_html(data, product, channel)

    return render_template('signatures.html',
                           product=product,
                           products=utils.get_products(),
                           channel=channel,
                           channels=utils.get_channels(),
                           data=data,
                           enumerate=enumerate)


def bug():
    bugid = request.args.get('id', '')
    bugid = utils.get_bug_number(bugid)
    data = models.Signatures.get_bybugid(bugid)
    data, links = signatures.prepare_bug_for_html(data)

    return render_template('bug.html',
                           data=data,
                           links=links,
                           bugid=bugid,
                           enumerate=enumerate)
