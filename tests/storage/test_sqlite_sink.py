"""storage 层测试：SQLiteSink 写入、去重、备份、字段收口落库。"""

from __future__ import annotations

import os

from fxharvest.storage.sqlite_sink import SQLiteSink


def _records(cls, items):
    return [cls.from_raw(it, source_slug="t") for it in items]


def test_write_and_dedup(tmp_db, job_record_cls):
    sink = SQLiteSink(tmp_db, job_record_cls, table="jobs", backup=False)
    recs = _records(job_record_cls, [
        {"职位名称": "后端", "公司": "A", "薪资": "20k"},
        {"职位名称": "前端", "公司": "A"},
    ])
    r = sink.write(recs, source_slug="t")
    assert r.received == 2 and r.inserted == 2 and r.updated == 0
    assert sink.total_count() == 2

    # 同 dedup_key 再写 → 更新而非新增
    r2 = sink.write(_records(job_record_cls, [{"职位名称": "后端", "公司": "A", "薪资": "25k"}]), source_slug="t")
    assert r2.inserted == 0 and r2.updated == 1
    assert sink.total_count() == 2
    sink.close()


def test_extra_folding_into_column(tmp_db, job_record_cls):
    """未声明字段应折叠进 extra_column（扩展信息）落库。"""
    sink = SQLiteSink(tmp_db, job_record_cls, table="jobs", backup=False)
    sink.write(_records(job_record_cls, [{"职位名称": "后端", "公司": "A", "薪资": "20k", "城市": "上海"}]), source_slug="t")
    rows = sink.db.query('SELECT 扩展信息 FROM jobs')
    assert "薪资" in rows[0][0] and "城市" in rows[0][0]
    sink.close()


def test_backup_creates_file(tmp_db, job_record_cls):
    sink = SQLiteSink(tmp_db, job_record_cls, table="jobs", backup=False)
    sink.write(_records(job_record_cls, [{"职位名称": "后端", "公司": "A"}]), source_slug="t")
    sink.backup_now()
    backup_dir = os.path.join(os.path.dirname(tmp_db), "database_backup")
    assert os.path.isdir(backup_dir) and os.listdir(backup_dir)
    sink.close()
