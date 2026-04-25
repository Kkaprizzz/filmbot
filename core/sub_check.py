from telethon import TelegramClient, functions, errors
from telethon.tl.types import PeerChannel
from telethon.tl.functions.messages import CheckChatInviteRequest
from telethon.errors import InviteHashInvalidError, InviteHashExpiredError
from typing import Union
import core.database as database
from core.config import settings

userbot = TelegramClient('session_name', settings.API_ID, settings.API_HASH)

error_msgs = ['chat not found', 'user not participant', 'bot was kicked']

async def check_subscription(user_id: int, channel_id: Union[str, int]) -> bool:
    try:
        if isinstance(channel_id, str) and 't.me/+' in channel_id:
            return True

        if isinstance(channel_id, int) or (isinstance(channel_id, str) and channel_id.lstrip('-').isdigit()):
            channel_id = int(channel_id)
            if str(channel_id).startswith("-100"):
                peer = PeerChannel(int(str(channel_id)[4:]))
                entity = await userbot.get_entity(peer)
            else:
                entity = await userbot.get_entity(channel_id)
        else:
            username = channel_id.replace("https://t.me/", "").replace("@", "")
            entity = await userbot.get_entity(username)

        await userbot(functions.channels.GetParticipantRequest(channel=entity, participant=user_id))
        return True

    except errors.UserNotParticipantError:
        return False
    except Exception as e:
        if any(err in str(e).lower() for err in error_msgs):
            return True
        return False

async def check_all_subscriptions(user_id: int) -> bool:
    sponsors = await database.get_sponsors(only_required=True)
    for sponsor in sponsors:
        check_target = sponsor['channelurl_private'] or sponsor['channelurl_pub']
        if not check_target:
            continue
        result = await check_subscription(user_id, check_target)
        if not result:
            return False
    return True
