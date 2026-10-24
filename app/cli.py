import argparse
import asyncio

from sqlalchemy import select

from app.core.security import generate_api_key
from app.db.models import Account, ApiKey, Application
from app.db.session import SessionLocal, engine


async def create_tenant(email: str, app_name: str) -> None:
    async with SessionLocal() as session:
        account = (
            await session.execute(select(Account).where(Account.email == email))
        ).scalar_one_or_none()
        if account is None:
            account = Account(email=email)
            session.add(account)
            await session.flush()

        application = Application(account_id=account.id, name=app_name)
        session.add(application)
        await session.flush()

        full_key, prefix, key_hash = generate_api_key()
        session.add(
            ApiKey(application_id=application.id, name="default", prefix=prefix, key_hash=key_hash)
        )
        await session.commit()

    print(f"application_id: {application.id}")
    print(f"api key (shown once): {full_key}")
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument("app_name")
    args = parser.parse_args()
    asyncio.run(create_tenant(args.email, args.app_name))


if __name__ == "__main__":
    main()