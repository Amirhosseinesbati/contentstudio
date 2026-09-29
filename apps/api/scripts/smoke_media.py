"""Verify scoped API access to the three seeded owned presentations."""

from fastapi.testclient import TestClient

from contentstudio.main import app


def main():
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@studio.test", "password": "DemoStudio!2026"},
        )
        login.raise_for_status()
        sources = client.get("/api/v1/sources").json()["items"]
        media = [source for source in sources if source["kind"] == "owned_media"]
        results = []
        for source in media:
            with client.stream("GET", f"/api/v1/sources/{source['id']}/media") as response:
                signature = next(response.iter_bytes())[:12]
                results.append({"id": source["id"], "status": response.status_code, "mime_type": response.headers.get("content-type"), "mp4_signature": b"ftyp" in signature})
        print(results)
        assert len(results) >= 3
        assert all(item["status"] == 200 and item["mp4_signature"] for item in results)


if __name__ == "__main__":
    main()
