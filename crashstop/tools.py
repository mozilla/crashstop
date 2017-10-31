# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bisect import bisect_left
import numpy as np
from . import config
from .const import INSTALLS


def get_global_ratios(data):
    res = {}
    for chan, info in data.items():
        R = len(info)
        for numbers in info.values():
            C = len(numbers)
            break
        x = np.empty((R, C), dtype=np.float64)
        for i, numbers in enumerate(info.values()):
            x[i, :] = [n[INSTALLS] for n in numbers.values()]

        meds = np.median(x, axis=1)
        notnull = meds != 0.
        means = np.mean(x, axis=1)
        stddevs = np.std(x, axis=1)
        ratios = stddevs[notnull] / means[notnull]
        res[chan] = float(np.median(ratios))
    return res


def get_threshold(x, min_value, ratio):
    if x == 0.:
        return min_value * (1. + ratio)
    return x * (1. + ratio)


def check_patch(numbers, pushdate, ratio, product, channel):
    min_value = config.get_min(product, channel)
    data = sorted(numbers.items(), key=lambda x: x[0])
    bids = [bid for bid, _ in data]
    numbers = [n[INSTALLS] for _, n in data]

    # pos is the position of the first build with the patch
    pos = bisect_left(bids, pushdate)

    if pos == 0:
        # all the builds contain the patch
        return np.mean(numbers) < min_value

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
        m = (i * m + x) / float(i + 1)

    if p == pos:
        in_spike = m
    else:
        in_spike = float(np.mean(without_patch[p:]))

    return get_threshold(mean_with_patch, min_value, 3. * ratio) < in_spike
