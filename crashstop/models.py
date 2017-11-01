# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata import utils as lmdutils
import sqlalchemy.dialects.postgresql as pg
import pytz
from . import signatures, utils
from . import db, app
from .logger import logger


class Buildid(db.Model):
    __tablename__ = 'buildid'

    pc = db.Column(db.String(3), primary_key=True)
    buildid = db.Column(db.DateTime(timezone=True), primary_key=True)
    version = db.Column(db.String(12))

    PRODS = {p[:2]: p for p in utils.get_products()}
    CHANS = {c[:1].upper(): c for c in utils.get_channels()}

    def __init__(self, pc, buildid, version):
        self.pc = pc
        self.buildid = buildid
        self.version = version

    @staticmethod
    def add_buildids(data, commit=True):
        for prod, i in data.items():
            for chan, j in i.items():
                pc = Buildid.get_pc(prod, chan)
                db.session.query(Buildid).filter_by(pc=pc).delete()
                for d, v in j:
                    db.session.add(Buildid(pc, d, v))
        if commit:
            db.session.commit()

    @staticmethod
    def get_versions(pc):
        query = db.session.query(Buildid.buildid, Buildid.version)
        versions = query.filter_by(pc=pc)
        res = {bid.astimezone(pytz.utc): v for bid, v in versions}
        return res

    @staticmethod
    def get_pc(product, channel):
        return product[:2] + channel[0].upper()

    @staticmethod
    def get_prod_chan(pc):
        p = pc[:2]
        c = pc[-1]

        return Buildid.PRODS[p], Buildid.CHANS[c]


class GlobalRatio(db.Model):
    __tablename__ = 'globalratio'

    pc = db.Column(db.String(3), primary_key=True)
    ratio = db.Column(db.Float)

    def __init__(self, pc, ratio):
        self.pc = pc
        self.ratio = ratio

    @staticmethod
    def put_data(data, commit=True):
        db.session.query(GlobalRatio).delete()
        for prod, i in data.items():
            for chan, ratio in i.items():
                pc = Buildid.get_pc(prod, chan)
                ins = pg.insert(GlobalRatio).values(pc=pc, ratio=ratio)
                upd = ins.on_conflict_do_update(index_elements=['pc'],
                                                set_=dict(ratio=ratio))
                db.session.execute(upd)
        if commit:
            db.session.commit()

    @staticmethod
    def get_ratios(pcs):
        pcs = [Buildid.get_pc(p, c) for p, c in pcs]
        grs = db.session.query(GlobalRatio).filter_by(GlobalRatio.pc.in_(pcs))
        res = {}
        for gr in grs:
            res[Buildid.get_prod_chan(gr.pc)] = gr.ratio
        return res


class Signatures(db.Model):
    __tablename__ = 'signatures'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pc = db.Column(db.String(3))
    signature = db.Column(db.String(512))
    bugid = db.Column(db.Integer, default=0)
    raw = db.Column(pg.ARRAY(db.Integer))
    installs = db.Column(pg.ARRAY(db.Integer))
    pushdate = db.Column(db.DateTime(timezone=True))
    success = db.Column(db.Boolean)

    def __init__(self, pc, signature, bugid, raw, installs, pushdate, success):
        self.pc = pc
        self.signature = signature
        self.bugid = bugid
        self.raw = raw
        self.installs = installs
        self.pushdate = pushdate
        self.success = success

    @staticmethod
    def put_data(data, bids, ratios):
        GlobalRatio.put_data(ratios, commit=False)
        Buildid.add_buildids(bids, commit=False)

        for product, i in data.items():
            for chan, j in i.items():
                pc = Buildid.get_pc(product, chan)
                db.session.query(Signatures).filter_by(pc=pc).delete()
                for sgn, infos in j.items():
                    for info in infos:
                        bugid = info['bugid']
                        numbers = info['numbers']
                        pushdate = info['pushdate']
                        success = info['success']
                        raw, installs = utils.get_raw_installs(numbers)
                        s = Signatures(pc, sgn, bugid, raw,
                                       installs, pushdate, success)
                        db.session.add(s)

        db.session.commit()

    @staticmethod
    def get_bypc(product, channel):
        pc = Buildid.get_pc(product, channel)
        sgns = db.session.query(Signatures).filter_by(pc=pc)
        versions = Buildid.get_versions(pc)

        d = {}
        res = {'signatures': d,
               'versions': versions}

        for sgn in sgns:
            d[sgn.signature] = {'bugid': sgn.bugid,
                                'pushdate': sgn.pushdate.astimezone(pytz.utc),
                                'raw': sgn.raw,
                                'installs': sgn.installs,
                                'success': sgn.success}

        return res

    @staticmethod
    def get_bybugid(bugid):
        q = db.session.query(Signatures.pc, Signatures.signature,
                             Signatures.raw, Signatures.installs,
                             Signatures.pushdate, Signatures.success)
        sgns = q.filter_by(bugid=bugid)

        data = {}
        versions = {}
        res = {'data': data,
               'versions': versions}
        cache = {}

        for sgn in sgns:
            prod, chan = Buildid.get_prod_chan(sgn.pc)
            if prod not in res:
                res[prod] = {}
            if chan not in res[prod]:
                res[prod][chan] = {}
            if sgn.pc not in versions:
                v = Buildid.get_versions(sgn.pc)
                d = sorted(v.keys())
                cache[sgn.pc] = d
                versions[(prod, chan)] = v

            dates = cache[sgn.pc]
            pushdate = sgn.pushdate.astimezone(pytz.utc)
            if prod not in data:
                data[prod] = {}
            if chan not in data[prod]:
                data[prod][chan] = {}
            data[prod][chan][sgn.signature] = {'pushdate': pushdate,
                                               'dates': dates,
                                               'raw': sgn.raw,
                                               'installs': sgn.installs,
                                               'success': sgn.success}
        return res


def put_data(date='today'):
    logger.info('Get data: started.')
    data, bids, ratios = signatures.get(date=date)
    Signatures.put_data(data, bids, ratios)
    logger.info('Get data: finished.')


def update(date='today'):
    d = lmdutils.get_date(date)
    logger.info('Update data for {}: started.'.format(d))
    put_data(date=date)
    logger.info('Update data for {}: finished.'.format(d))


def create(date='today'):
    engine = db.get_engine(app)
    if not engine.dialect.has_table(engine, 'buildid'):
        d = lmdutils.get_date(date)
        logger.info('Create data for {}: started.'.format(d))
        db.create_all()
        put_data(date=date)
        logger.info('Create data for {}: finished.'.format(d))
