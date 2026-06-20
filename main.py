import os

if os.path.exists('.env'):
    import asyncio

    from dotenv import load_dotenv

    load_dotenv('.env')

    from components.core import BotClient
    from components.log import main_logger as logger

    logger.info('.env file read.')
else:
    raise FileNotFoundError(
        'No .env file found. Please create a .env file with the necessary environment variables.'
    )


async def main() -> None:
    bot = BotClient()
    try:
        async with bot:
            await bot.start(os.getenv('BOT_TOKEN', ''))
    except Exception as e:
        logger.exception(f'Error starting bot: {e}')


if __name__ == '__main__':
    asyncio.run(main())
