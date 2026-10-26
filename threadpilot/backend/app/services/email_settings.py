"""Persistent owner email preferences and customer address book."""
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, field_validator
from fastapi import HTTPException
from .outlook_service import OutlookService
from .dashboard_service import LOCAL
import re


def email(value):
    value = value.strip()
    if len(value) > 254 or not re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+', value):
        raise ValueError('Enter a valid email address.')
    return value


class CustomerContact(BaseModel):
    customer: str = Field(min_length=1, max_length=160)
    name: str = Field(default='', max_length=160)
    email: str

    _email = field_validator('email')(email)

    @field_validator('customer', 'name')
    @classmethod
    def trim(cls, value, info):
        value = value.strip()
        if info.field_name == 'customer' and not value:
            raise ValueError('Customer name is required.')
        return value


class EmailPreferences(BaseModel):
    version: int = Field(ge=0)
    manager_email: str
    manager_name: str = Field(default='Manager', max_length=100)
    briefing_enabled: bool = False
    subject_prefix: str = Field(default='ThreadPilot morning briefing', min_length=1, max_length=120)
    customers: list[CustomerContact] = Field(default_factory=list, max_length=200)
    departments: dict[str, str] = Field(default_factory=dict)

    @field_validator('departments')
    @classmethod
    def department_emails(cls, values):
        if set(values) - {'KNITTING','ASSEMBLY','WASHING','PACKING'}:
            raise ValueError('Unknown department.')
        return {key:email(value) if value.strip() else '' for key,value in values.items()}

    _manager_email = field_validator('manager_email')(email)

    @field_validator('subject_prefix')
    @classmethod
    def subject(cls, value):
        if not value.strip() or any(c in value for c in '\r\n\x00'):
            raise ValueError('Enter a valid subject prefix.')
        return value.strip()


class EmailSettings:
    def __init__(self, settings):
        self.outlook = OutlookService(settings)

    def read(self):
        with self.outlook.db() as db:
            return self.read_in(db)

    def read_in(self, db):
        return self.outlook.get(db, 'email_preferences', {
            'version': 0, 'manager_email': '1098214258@qq.com', 'manager_name': 'Manager',
            'briefing_enabled': False, 'subject_prefix': 'ThreadPilot morning briefing',
            'customers': [], 'start_day': None, 'updated_at': None,
            'time': '07:00', 'timezone': 'Asia/Shanghai'})

    def save(self, body, now=None):
        from ..business_clock import BusinessClock
        now = (now or BusinessClock(self.outlook.settings).now()).astimezone(LOCAL)
        with self.outlook.db() as db:
            old = self.read_in(db)
            if old['version'] != body.version:
                raise HTTPException(409, 'Email settings changed. Reload before saving.')
            if body.briefing_enabled and not self.outlook.get(db, 'account'):
                raise HTTPException(409, 'Connect Outlook before enabling automatic briefings.')
            start_day = old.get('start_day')
            clock = BusinessClock(self.outlook.settings).read() or {}
            if old.get('clock_run_id','') != clock.get('run_id',''):
                start_day = clock.get('schedule_start_day')
            if body.briefing_enabled and not old['briefing_enabled']:
                start_day = (now.date() + timedelta(days=int(now.hour >= 7))).isoformat()
            saved = {**body.model_dump(), 'version': old['version'] + 1, 'start_day': start_day,
                     'clock_run_id':clock.get('run_id',''),
                     'updated_at': now.isoformat(), 'time': '07:00', 'timezone': 'Asia/Shanghai'}
            self.outlook.put(db, 'email_preferences', saved)
            return saved
