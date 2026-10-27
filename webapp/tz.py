"""Múi giờ hiển thị của hệ thống.

created_at trong DB luôn lưu UTC — đúng chuẩn và không phụ thuộc nơi chạy.
Mọi truy vấn theo ngày và mọi chỗ hiển thị đều quy đổi sang giờ Việt Nam,
để nhân viên kho thấy đúng ngày làm việc của mình.
"""
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7), 'ICT')

# Dùng làm modifier trong SQL: DATE(created_at, VN_OFFSET)
VN_OFFSET = '+7 hours'


def to_vn(value):
    """Đổi timestamp UTC (chuỗi ISO hoặc datetime) sang datetime giờ VN."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(VN_TZ)


def format_vn(value, fmt='%d/%m/%Y %H:%M'):
    """Chuỗi thời gian giờ VN để hiển thị. Không parse được thì trả lại nguyên bản."""
    converted = to_vn(value)
    return converted.strftime(fmt) if converted else (value or '')
