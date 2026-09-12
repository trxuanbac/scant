import pytest
from app.services.storage.storage_provider import LocalStorageProvider, S3StorageProvider
from app.services.storage.signed_url_service import signed_url_service
from app.services.storage.deduplication_service import deduplication_service


@pytest.mark.asyncio
async def test_storage_providers_unit():
    # 1. S3 Storage Provider
    s3 = S3StorageProvider(bucket_name="test-saas-bucket")
    res = await s3.put_object("reports/q3_financial.pdf", b"%PDF-1.4 Mock Financial PDF", "application/pdf")
    assert res["checksum_sha256"] is not None
    assert await s3.exists("reports/q3_financial.pdf") is True
    data = await s3.get_object("reports/q3_financial.pdf")
    assert data.startswith(b"%PDF")
    await s3.delete_object("reports/q3_financial.pdf")
    assert await s3.exists("reports/q3_financial.pdf") is False


def test_signed_url_service_security():
    storage_key = "/tmp/private_audit_report.docx"
    user_id = "user-finance-101"

    # 1. Valid signed token
    token = signed_url_service.generate_signed_token(storage_key, user_id, expires_in_seconds=3600)
    is_valid, decoded_key, err = signed_url_service.verify_and_decode_token(token)
    assert is_valid is True
    assert decoded_key == storage_key
    assert err is None

    # 2. Tampered token
    tampered_token = token[:-4] + "AAAA"
    is_valid_t, _, err_t = signed_url_service.verify_and_decode_token(tampered_token)
    assert is_valid_t is False
    assert err_t is not None

    # 3. Expired token
    expired_token = signed_url_service.generate_signed_token(storage_key, user_id, expires_in_seconds=-10)
    is_valid_exp, _, err_exp = signed_url_service.verify_and_decode_token(expired_token)
    assert is_valid_exp is False
    assert "hết hạn" in err_exp


def test_deduplication_hash():
    data1 = b"Strategic Planning 2026 Analysis"
    data2 = b"Strategic Planning 2026 Analysis"
    data3 = b"Different Content"

    h1 = deduplication_service.compute_sha256(data1)
    h2 = deduplication_service.compute_sha256(data2)
    h3 = deduplication_service.compute_sha256(data3)

    assert h1 == h2
    assert h1 != h3
