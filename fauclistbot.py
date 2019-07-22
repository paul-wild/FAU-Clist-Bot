#!/usr/bin/env python

import json, logging, urllib, locale, time, yaml

from functools import partial
from datetime import datetime, timedelta
from pytz import timezone, utc
from telegram import ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

try:
    cfg = yaml.safe_load(open("config.yaml", 'r'))
except yaml.YAMLError as exc:
    print(exc)

# These must be kept secret.
clist_user = cfg['clist_user']
clist_api_key = cfg['clist_api_key']
telegram_token = cfg['telegram_token']

# Date formats as used on Clist and as displayed on Telegram.
clist_dateformat = '%Y-%m-%dT%H:%M:%S'
display_dateformat = '%a %d.%m. %H:%M'

# Time zone used to display times on Telegram.
display_timezone = timezone('Europe/Berlin')

# Time intervals before a contest with which to send out reminders.
reminder_intervals = [timedelta(days=1), timedelta(hours=2)]

# We are only interested in contests from certain sites,
# so we filter on those ids.
resource_ids = cfg['resource_ids']

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)


# Set of Telegram chat IDs to which contest reminders will be sent.
subscribers = set()

def start(update, context):
    sub = update.message.chat_id
    subscribers.add(sub)
    logger.info('Added %d to list of subscribers.', sub)
    logger.info('Current subscribers: %s', str(subscribers))
    update.message.reply_text('Subscribed to contest updates!')

def unsubscribe(update, context):
    sub = update.message.chat_id
    subscribers.remove(sub)
    logger.info('Removed %d from list of subscribers.', sub)
    logger.info('Current subscribers: %s', str(subscribers))
    update.message.reply_text('Unsubscribed from contest reminders.')

def error(update, context):
    # Log Errors caused by Updates.
    logger.warning('Update "%s" caused error "%s".', update, context.error)


# Get a list of all contests with a start time between `start` and `start+delta`.
# `start` must be in UTC.
def get_contests(start, delta=timedelta(weeks=2)):
    url = 'https://clist.by/api/v1/contest/?username=' + clist_user \
        + '&api_key=' + clist_api_key \
        + '&resource__id__in=' + ','.join(map(str,resource_ids)) \
        + '&start__gt=' + start.strftime(clist_dateformat) \
        + '&start__lt=' + (start+delta).strftime(clist_dateformat) \
        + '&order_by=start'
    response = urllib.urlopen(url)
    return json.loads(response.read())['objects']
    # data = [x for x in data if x['resource']['id'] == 1]
    # print json.dumps(data, indent=4)


# Parse a time from Clist and convert it to the proper timezone.
def parse_time(time_str):
    utctime = utc.localize(datetime.strptime(time_str, clist_dateformat))
    return utctime.astimezone(display_timezone)


# Given a contest in JSON format, return relevant information in Markdown format.
def to_markdown(contest):
    start = parse_time(contest['start'])
    end = parse_time(contest['end'])
    duration = end-start
    return '%s, %s [%s](%s)' % (start.strftime(display_dateformat),
                                str(duration)[:-3],
                                contest['event'],
                                contest['href'])


def list_contests(update, context):
    contests = get_contests(datetime.utcnow())[:6]
    message = 'Upcoming contests:\n' \
            + ('\n'.join(map(to_markdown, contests)) if contests else 'No contests found!')
    # update.message.reply_markdown('\n'.join(map(to_markdown, contests)))
    logger.info('Sent list with %d upcoming contests.', len(contests))
    context.bot.send_message(update.message.chat_id, message,
                             parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


# Check if the job queue of `context` already contains reminders for `contest`.
def is_already_scheduled(contest, context):
    for job in context.job_queue.jobs():
        if job.name == contest['id']:
            return True
    return False


def round_to_nearest_minute(delta):
    seconds = delta.total_seconds()
    return timedelta(minutes=round(seconds/60.0))


# Send reminder for `contest` to all subscribers.
def send_reminder(context, contest):
    delta = parse_time(contest['start']) - datetime.now(utc).astimezone(display_timezone)
    delta = round_to_nearest_minute(delta)
    message = 'Reminder: [%s](%s) starts in %s' % (contest['event'], contest['href'], str(delta))

    for sub in subscribers:
        context.bot.send_message(chat_id=sub, text=message,
                                 parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

    logger.info('Sent out reminder for "%s" (id=%d, delta=%s).',
                contest['event'], contest['id'], str(delta))


# Check clist for new contests and schedule reminders for them.
def schedule_reminders(context):
    contests = get_contests(datetime.utcnow())
    for contest in contests:
        if is_already_scheduled(contest, context):
            continue
        for delta in reminder_intervals:
            remindertime = parse_time(contest['start']) - delta
            if remindertime < datetime.now(utc).astimezone(display_timezone):
                continue

            context.job_queue.run_once(partial(send_reminder, contest=contest),
                                       remindertime.replace(tzinfo=None),
                                       name=contest['id'])

            logger.info('Scheduled reminder for "%s" (id=%d) at %s.',
                        contest['event'], contest['id'], str(remindertime))

    jobnames = sorted(job.name for job in context.job_queue.jobs())
    logger.info('Current jobs: ' + ' '.join(map(str,jobnames)))



def main():
    # locale.setlocale(locale.LC_TIME, 'de_DE.utf8')

    updater = Updater(telegram_token, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("list", list_contests))
    dispatcher.add_handler(CommandHandler("unsubscribe", unsubscribe))

    # Query the Clist API once every hour for new contests.
    jobqueue = updater.job_queue
    jobqueue.run_repeating(schedule_reminders, interval=3600, first=0)

    dispatcher.add_error_handler(error)

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
