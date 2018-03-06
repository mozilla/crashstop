# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bisect import bisect_left
import numpy as np
from . import config
from .const import INSTALLS


def get_global_ratios(data):
    R = len(data)
    for numbers in data.values():
        C = len(numbers)
        break
    x = np.empty((R, C), dtype=np.float64)
    for i, numbers in enumerate(data.values()):
        x[i, :] = [n[INSTALLS] for n in numbers]

    meds = np.median(x, axis=1)
    notnull = meds != 0.
    means = np.mean(x, axis=1)
    stddevs = np.std(x, axis=1)
    ratios = stddevs[notnull] / means[notnull]

    return float(np.median(ratios))


def get_threshold(x, min_value, ratio):
    if x == 0.:
        return min_value * (1. + ratio)
    return x * (1. + ratio)


def check_patch(numbers, pushdate, bids, ratio, min_value):
    numbers = [n[INSTALLS] for n in numbers]

    # pos is the position of the first build with the patch
    pos = bisect_left(bids, pushdate)

    if pos == len(bids):
        return False

    if pos == 0:
        # all the builds contain the patch
        return bool(np.mean(numbers) < min_value)

    with_patch = numbers[pos:]

    mean_with_patch = float(np.mean(with_patch))
    if mean_with_patch == 0.:
        return True

    without_patch = numbers[:pos]
    m = float(without_patch[0])
    p = pos
    for i in range(1, pos):
        threshold = get_threshold(m, min_value, ratio)
        x = float(numbers[i])
        if x >= threshold:
            p = i
            break
        i = float(i)
        m = (i * m + x) / (i + 1.)

    if p == pos:
        in_spike = m
    else:
        in_spike = float(np.mean(without_patch[p:]))

    return get_threshold(mean_with_patch, min_value, 3. * ratio) < in_spike


def compute_success(data, patches, bids, ratios):
    res = {}
    for prod, i in data.items():
        bids_prod = bids[prod]
        ratios_prod = ratios[prod]
        res[prod] = res_prod = {}
        for chan, j in i.items():
            ratio = ratios_prod[chan]
            bids_chan = [b[0] for b in bids_prod[chan]]
            res_prod[chan] = res_chan = {}
            min_value = config.get_min(prod, chan)
            for sgn, numbers in j.items():
                patch = patches[sgn]
                for bug, k in patch.items():
                    pushdate = k.get(chan)
                    if not pushdate:
                        continue

                    if bids_chan[0] > pushdate:
                        continue

                    success = check_patch(numbers, pushdate,
                                          bids_chan, ratio,
                                          min_value)

                    if sgn not in res_chan:
                        res_chan[sgn] = []
                    res_chan[sgn].append({'numbers': numbers,
                                          'pushdate': pushdate,
                                          'bugid': bug,
                                          'success': success})
    return res
