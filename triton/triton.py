""" "Triton Telegram bot"""

import datetime
import logging
import typing as t
from pathlib import Path

import dotenv
import pytz
import yaml
from operate.cli import OperateApp
from operate.constants import OPERATE
from operate.operate_types import Chain
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from triton.chain import get_olas_price, get_slots
from triton.constants import (
    AGENT_BALANCE_THRESHOLD,
    AUTOCLAIM,
    AUTOCLAIM_DAY,
    AUTOCLAIM_HOUR_UTC,
    CHAT_ID,
    GNOSISSCAN_ADDRESS_URL,
    GNOSISSCAN_TX_URL,
    LOCAL_TIMEZONE,
    MANUAL_CLAIM,
    OPERATE_USER_PASSWORD,
    SAFE_BALANCE_THRESHOLD,
    TELEGRAM_TOKEN,
)
from triton.service import TritonService
from triton.tools import escape_markdown_v2

logger = logging.getLogger("telegram_bot")

# Secrets
dotenv.load_dotenv(override=True)


def run_triton() -> None:  # pylint: disable=too-many-statements,too-many-locals
    """Main"""

    # Load configuration
    with open("config.yaml", "r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    # Instantiate the services
    services: t.Dict[str, TritonService] = {}
    for operator_name, operate_path in config["operators"].items():
        operate = OperateApp(Path(operate_path) / OPERATE)
        operate.password = OPERATE_USER_PASSWORD
        for (
            service
        ) in (
            operate.service_manager()._get_all_services()  # pylint: disable=protected-access
        ):
            services[f"{operator_name}-{service.name}"] = TritonService(
                operate=operate,
                service_config_id=service.service_config_id,
            )

    # Commands
    async def staking_status(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,  # pylint: disable=unused-argument
    ) -> None:
        messages = []
        total_rewards = 0.0
        for service_name, service in services.items():
            status = service.get_staking_status()
            total_rewards += float(status["accrued_rewards"].split(" ")[0])
            messages.append(
                f"[{service_name}] {status['accrued_rewards']} "
                f"""[{status['mech_requests_this_epoch']}/{status['required_mech_requests']}]
Staking program: {status['metadata']['name']}
Next epoch: {status['epoch_end']}"""
            )

        olas_price = get_olas_price()
        rewards_value = total_rewards * olas_price if olas_price else None
        message = f"Total rewards = {total_rewards:g} OLAS"
        if rewards_value:
            message += f" [${rewards_value:g}]"
        messages.append(message)

        if update.message is None:
            logger.error("Cannot send message, update.message is None")
            return

        await update.message.reply_text(text=("\n\n").join(messages))

    async def balance(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ):  # pylint: disable=unused-argument
        messages = []
        for service_name, service in services.items():
            balances = service.check_balance()
            agent_native_balance = balances["agent_eoa_native_balance"]
            safe_native_balance = balances["service_safe_native_balance"]
            safe_olas_balance = balances["service_safe_olas_balance"]
            master_eoa_native_balance = balances["master_eoa_native_balance"]
            master_safe_native_balance = balances["master_safe_native_balance"]

            if service.master_wallet.safes is None:
                raise ValueError("Master wallet safes not found")

            message = (
                r"\["
                + escape_markdown_v2(service_name)
                + r"]"
                + f"\n[Agent EOA]({GNOSISSCAN_ADDRESS_URL.format(address=service.agent_address)}) = {agent_native_balance:g} xDAI"  # noqa: E501
                + f"\n[Service Safe]({GNOSISSCAN_ADDRESS_URL.format(address=service.service_safe)}) = {safe_native_balance:g} xDAI  {safe_olas_balance:g} OLAS"  # noqa: E501
                + f"\n[Master EOA]({GNOSISSCAN_ADDRESS_URL.format(address=service.master_wallet.crypto.address)}) = {master_eoa_native_balance:g} xDAI"  # noqa: E501
                + f"\n[Master Safe]({GNOSISSCAN_ADDRESS_URL.format(address=service.master_wallet.safes[Chain.from_string(service.service.home_chain)])}) = {master_safe_native_balance:g} xDAI"  # type: ignore[attr-defined]  # noqa: E501
            )

            messages.append(message)

        if update.message is None:
            logger.error("Cannot send message, update.message is None")
            return

        await update.message.reply_text(
            text=("\n\n").join(messages),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

    async def claim(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ):  # pylint: disable=unused-argument
        """Claim rewards"""

        if not update.message:
            logger.error("Cannot send message, update.message is None")
            return

        if not MANUAL_CLAIM:
            await update.message.reply_text(text="Manual claim is disabled")
            return

        messages = []
        for service_name, service in services.items():
            tx_hash = service.claim_rewards()
            if not tx_hash:
                continue

            messages.append(
                f"[{service_name}] Sent the [claim transaction]({GNOSISSCAN_TX_URL.format(tx_hash=tx_hash)}). "
                "Rewards will be sent to the Service Safe."
            )

        await update.message.reply_text(
            text=("\n").join(messages),
        )

    async def withdraw(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ):  # pylint: disable=unused-argument
        """Withdraw rewards"""
        if not update.message:
            logger.error("Cannot send message, update.message is None")
            return

        messages = []
        for service_name, service in services.items():
            tx_hash, value = service.withdraw_rewards()
            message = (
                r"\["
                + escape_markdown_v2(service_name)
                + r"] "
                + f"Sent the [withdrawal transaction]({GNOSISSCAN_TX_URL.format(tx_hash=tx_hash)}). "
                + f"{value:g} OLAS sent from the Service Safe to [{service.withdrawal_address}]"
                + f"({GNOSISSCAN_ADDRESS_URL.format(address=service.withdrawal_address)}) #withdraw"
                if tx_hash
                else r"\["
                + escape_markdown_v2(service_name)
                + r"] "
                + "Cannot withdraw rewards"
            )

            messages.append(message)

        await update.message.reply_text(
            text=("\n\n").join(messages),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

    async def slots(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ):  # pylint: disable=unused-argument
        if not update.message:
            logger.error("Cannot send message, update.message is None")
            return

        slots = get_slots()

        messages = [
            f"[{contract_name}] {n_slots} available slots"
            for contract_name, n_slots in slots.items()
        ]

        await update.message.reply_text(
            text=("\n").join(messages),
        )

    async def scheduled_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            logger.error("Cannot send message, update.message is None")
            return

        jobs = context.job_queue.jobs() if context.job_queue else []

        if not jobs:
            await update.message.reply_text("No scheduled jobs")
            return

        message = ""
        for job in jobs:
            next_execution = (
                job.next_t.astimezone(pytz.timezone(LOCAL_TIMEZONE)).strftime(
                    "%Y-%m-%d %H:%M:%S %Z"
                )
                if job.next_t
                else "N/A"
            )
            message += f"• {job.name}: {next_execution}\n"

        await update.message.reply_text(message)

    # Tasks
    async def start(context: ContextTypes.DEFAULT_TYPE):
        """Start"""
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text="Triton has started",
        )

    async def balance_check(context: ContextTypes.DEFAULT_TYPE):
        logger.info("Running balance check task")
        for service_name, triton_service in services.items():
            balances = triton_service.check_balance()
            agent_native_balance = balances["agent_eoa_native_balance"]
            safe_native_balance = balances["service_safe_native_balance"]

            if agent_native_balance < AGENT_BALANCE_THRESHOLD:
                message = f"[{service_name}] [Agent EOA]({GNOSISSCAN_ADDRESS_URL.format(address=triton_service.agent_address)}) balance is {agent_native_balance:g} xDAI"  # noqa: E501
                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True,
                )

            if safe_native_balance < SAFE_BALANCE_THRESHOLD:
                message = f"[{service_name}] [Service Safe]({GNOSISSCAN_ADDRESS_URL.format(address=triton_service.service_safe)}) balance is {safe_native_balance:g} xDAI"  # noqa: E501
                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True,
                )

    async def post_init(app):
        # await app.bot.set_my_name("Triton")
        await app.bot.set_my_description("A bot to manage Olas staked services")
        await app.bot.set_my_short_description("A bot to manage Olas staked services")
        await app.bot.set_my_commands(
            [
                ("staking_status", "Staking status"),
                ("balance", "Check wallet balances"),
                ("claim", "Claim rewards"),
                ("withdraw", "Withdraw rewards"),
                ("slots", "Check available staking slots"),
                ("jobs", "Check the scheduled jobs"),
            ]
        )

    async def autoclaim(context: ContextTypes.DEFAULT_TYPE):
        logger.info("Running autoclaim task")

        if not AUTOCLAIM:
            logger.info("Autoclaim task is disabled")
            return

        messages = []

        # Claim
        for service in services.values():
            service.claim_rewards()

        # Withdraw
        for service_name, service in services.items():
            tx_hash, value = service.withdraw_rewards()
            message = (
                r"\["
                + escape_markdown_v2(service_name)
                + r"] "
                + f"(Autoclaim) Sent the [withdrawal transaction]({GNOSISSCAN_TX_URL.format(tx_hash=tx_hash)}). "
                + f"{value:g} OLAS sent from the Safe to [{service.withdrawal_address}]"
                + f"({GNOSISSCAN_ADDRESS_URL.format(address=service.withdrawal_address)}) #withdraw"
                if tx_hash
                else r"\["
                + escape_markdown_v2(service_name)
                + r"] "
                + "(Autoclaim) Cannot withdraw rewards"
            )

            messages.append(message)

        if not messages:
            logger.info("No rewards to withdraw")
            return

        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=("\n\n").join(messages),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

    # Create bot
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    if app.job_queue is None:
        raise RuntimeError("Job queue is not available")

    job_queue = app.job_queue

    # Add commands
    app.add_handler(CommandHandler("staking_status", staking_status))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("claim", claim))
    app.add_handler(CommandHandler("withdraw", withdraw))
    app.add_handler(CommandHandler("slots", slots))
    app.add_handler(CommandHandler("jobs", scheduled_jobs))

    # Add tasks
    job_queue.run_once(start, when=3)  # in 3 seconds
    job_queue.run_repeating(
        balance_check,
        interval=datetime.timedelta(hours=1),
        first=5,  # in 5 seconds
    )
    job_queue.run_monthly(
        autoclaim,
        day=AUTOCLAIM_DAY,
        when=datetime.time(
            hour=AUTOCLAIM_HOUR_UTC, minute=0, second=0, microsecond=0, tzinfo=None
        ),
    )

    # Start
    logger.info("Starting bot")
    app.run_polling()
