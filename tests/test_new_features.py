"""
Tests for new features: Image Generator, Telegram Bot, Discord Bot, RAG Engine,
Cron Expressions, Remote Skill Marketplace
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture()
def client():
    from orbit.orbit.server import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


class TestImageGenerator:
    def test_singleton(self):
        from orbit.orbit.core.image_generator import ImageGenerator

        a = ImageGenerator()
        b = ImageGenerator()
        assert a is b

    def test_status_shape(self):
        from orbit.orbit.core.image_generator import ImageGenerator

        gen = ImageGenerator()
        s = gen.get_status()
        assert "dalle3_available" in s
        assert "sd_available" in s
        assert "flux_available" in s
        assert "stats" in s

    def test_generate_missing_key(self):
        from orbit.orbit.core.image_generator import ImageGenerator, ImageRequest

        gen = ImageGenerator()
        old_key = gen._openai_key
        gen._openai_key = ""
        result = gen.generate(ImageRequest(prompt="test", model="dalle3"))
        assert result.error
        gen._openai_key = old_key

    def test_cache(self):
        from orbit.orbit.core.image_generator import ImageGenerator

        gen = ImageGenerator()
        gen.clear_cache()
        assert len(gen._cache) == 0

    def test_recent_images(self):
        from orbit.orbit.core.image_generator import ImageGenerator

        gen = ImageGenerator()
        recent = gen.get_recent(5)
        assert isinstance(recent, list)


class TestTelegramBot:
    def test_singleton(self):
        from orbit.orbit.core.telegram_bot import TelegramBot

        a = TelegramBot()
        b = TelegramBot()
        assert a is b

    def test_status_no_token(self):
        from orbit.orbit.core.telegram_bot import TelegramBot

        bot = TelegramBot()
        old = bot._token
        bot._token = ""
        s = bot.get_status()
        assert s["running"] is False
        assert s["token_set"] is False
        bot._token = old

    def test_start_no_token(self):
        from orbit.orbit.core.telegram_bot import TelegramBot

        bot = TelegramBot()
        old = bot._token
        bot._token = ""
        result = bot.start()
        assert "error" in result
        bot._token = old

    def test_history(self):
        from orbit.orbit.core.telegram_bot import TelegramBot

        bot = TelegramBot()
        h = bot.get_history(10)
        assert isinstance(h, list)

    def test_handler(self):
        from orbit.orbit.core.telegram_bot import TelegramBot

        bot = TelegramBot()
        called = []
        bot.set_message_handler(lambda msg: called.append(msg.text) or "ok")
        assert bot._message_handler is not None


class TestDiscordBot:
    def test_singleton(self):
        from orbit.orbit.core.discord_bot import DiscordBot

        a = DiscordBot()
        b = DiscordBot()
        assert a is b

    def test_status_no_token(self):
        from orbit.orbit.core.discord_bot import DiscordBot

        bot = DiscordBot()
        old = bot._token
        bot._token = ""
        s = bot.get_status()
        assert s["running"] is False
        assert s["token_set"] is False
        bot._token = old

    def test_start_no_token(self):
        from orbit.orbit.core.discord_bot import DiscordBot

        bot = DiscordBot()
        old = bot._token
        bot._token = ""
        result = bot.start()
        assert "error" in result
        bot._token = old

    def test_history(self):
        from orbit.orbit.core.discord_bot import DiscordBot

        bot = DiscordBot()
        h = bot.get_history(10)
        assert isinstance(h, list)


class TestRAGEngine:
    def test_singleton(self):
        from orbit.orbit.core.rag_engine import RAGEngine

        a = RAGEngine()
        b = RAGEngine()
        assert a is b

    def test_ingest_text(self):
        from orbit.orbit.core.rag_engine import RAGEngine

        rag = RAGEngine()
        result = rag.ingest(
            "Hello world, this is a test document about AI", source="test"
        )
        assert result["ingested"] >= 1

    def test_query(self):
        from orbit.orbit.core.rag_engine import RAGEngine

        rag = RAGEngine()
        rag.ingest("The capital of France is Paris. France is in Europe.")
        results = rag.query("capital of France")
        assert len(results) > 0

    def test_status(self):
        from orbit.orbit.core.rag_engine import RAGEngine

        rag = RAGEngine()
        s = rag.get_status()
        assert "documents" in s
        assert "chunks" in s

    def test_delete(self):
        from orbit.orbit.core.rag_engine import RAGEngine

        rag = RAGEngine()
        result = rag.ingest("Delete me later", source="test_del")
        if result["doc_ids"]:
            ok = rag.delete(result["doc_ids"][0])
            assert ok

    def test_clear(self):
        from orbit.orbit.core.rag_engine import RAGEngine

        rag = RAGEngine()
        r = rag.clear()
        assert r["cleared"] is True


class TestCronExpressions:
    def test_parse_star(self):
        from orbit.orbit.core.task_scheduler import TaskScheduler

        values = TaskScheduler._parse_cron_field("*", 0, 59)
        assert len(values) == 60

    def test_parse_specific(self):
        from orbit.orbit.core.task_scheduler import TaskScheduler

        values = TaskScheduler._parse_cron_field("0,15,30,45", 0, 59)
        assert values == [0, 15, 30, 45]

    def test_parse_range(self):
        from orbit.orbit.core.task_scheduler import TaskScheduler

        values = TaskScheduler._parse_cron_field("9-17", 0, 23)
        assert values == list(range(9, 18))

    def test_parse_step(self):
        from orbit.orbit.core.task_scheduler import TaskScheduler

        values = TaskScheduler._parse_cron_field("*/5", 0, 59)
        assert values == list(range(0, 60, 5))

    def test_cron_next_run(self):
        from orbit.orbit.core.task_scheduler import TaskScheduler

        sched = TaskScheduler()
        now = time.time()
        next_run = sched._cron_next_run("*/5 * * * *", now)
        assert next_run > now
        assert next_run - now <= 330

    def test_add_task_with_cron(self):
        from orbit.orbit.core.task_scheduler import TaskScheduler

        sched = TaskScheduler()
        task = sched.add_task("cron_test", cron="*/10 * * * *")
        assert task.cron == "*/10 * * * *"
        assert task.next_run > 0
        sched.remove_task(task.task_id)


class TestRemoteSkillMarketplace:
    def test_singleton(self):
        from orbit.orbit.core.remote_skill_marketplace import RemoteSkillMarketplace

        a = RemoteSkillMarketplace()
        b = RemoteSkillMarketplace()
        assert a is b

    def test_builtin_skills(self):
        from orbit.orbit.core.remote_skill_marketplace import RemoteSkillMarketplace

        mp = RemoteSkillMarketplace()
        skills = mp.get_builtin_skills()
        assert len(skills) >= 5

    def test_categories(self):
        from orbit.orbit.core.remote_skill_marketplace import RemoteSkillMarketplace

        mp = RemoteSkillMarketplace()
        cats = mp.get_categories()
        assert "productivity" in cats

    def test_status(self):
        from orbit.orbit.core.remote_skill_marketplace import RemoteSkillMarketplace

        mp = RemoteSkillMarketplace()
        s = mp.get_status()
        assert "installed_count" in s

    def test_installed_list(self):
        from orbit.orbit.core.remote_skill_marketplace import RemoteSkillMarketplace

        mp = RemoteSkillMarketplace()
        installed = mp.get_installed()
        assert isinstance(installed, list)


class TestImageGenAPI:
    def test_status_endpoint(self, client):
        resp = client.get("/api/image-gen/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "dalle3_available" in data

    def test_generate_no_prompt(self, client):
        resp = client.post("/api/image-gen/generate", json={})
        assert resp.status_code == 400

    def test_recent(self, client):
        resp = client.get("/api/image-gen/recent")
        assert resp.status_code == 200


class TestTelegramAPI:
    def test_status_endpoint(self, client):
        resp = client.get("/api/telegram/status")
        assert resp.status_code == 200

    def test_send_no_chat_id(self, client):
        resp = client.post("/api/telegram/send", json={"text": "hi"})
        assert resp.status_code == 400


class TestDiscordAPI:
    def test_status_endpoint(self, client):
        resp = client.get("/api/discord/status")
        assert resp.status_code == 200

    def test_send_no_channel(self, client):
        resp = client.post("/api/discord/send", json={"text": "hi"})
        assert resp.status_code == 400


class TestRAGAPI:
    def test_status_endpoint(self, client):
        resp = client.get("/api/rag/status")
        assert resp.status_code == 200

    def test_ingest_empty(self, client):
        resp = client.post("/api/rag/ingest", json={})
        assert resp.status_code == 400

    def test_query_empty(self, client):
        resp = client.post("/api/rag/query", json={})
        assert resp.status_code == 400


class TestMarketplaceAPI:
    def test_status_endpoint(self, client):
        resp = client.get("/api/marketplace/status")
        assert resp.status_code == 200

    def test_browse(self, client):
        resp = client.get("/api/marketplace/browse")
        assert resp.status_code == 200

    def test_categories(self, client):
        resp = client.get("/api/marketplace/categories")
        assert resp.status_code == 200

    def test_installed(self, client):
        resp = client.get("/api/marketplace/installed")
        assert resp.status_code == 200

    def test_install_no_id(self, client):
        resp = client.post("/api/marketplace/install", json={})
        assert resp.status_code == 400
