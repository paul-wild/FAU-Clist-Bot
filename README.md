# FAU-Clist-Bot

Telegram bot to post contest reminders about programming contests.

The contest list is obtained from the API on [Clist](https://clist.by/).

To use the bot, you need to add a `config.yaml` file with the following contents:

    clist_user: <your username on clist.by>
    clist_api_key: <your clist api key>
    telegram_token: <the telegram token of your bot>
    resource_ids: <list of resource IDs you wish to include, one per line>

You can find a list of resource IDs [here](https://clist.by/api/v1/resource/).
