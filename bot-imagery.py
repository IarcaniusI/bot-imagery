import re
import time
import sys
import praw
import argparse
import json
import random
import signal
from datetime import datetime

PROCESS_NAME = "bot-imagery"
BOT_NAME = "Imagery"
NO_NOTIFY =False

# register bot for use: https://www.reddit.com/prefs/apps
def signal_term_handler(signal, frame):
    exit_time = datetime.now().isoformat().replace("T", " ")
    print(exit_time, '|', PROCESS_NAME, 'terminated')
    sys.exit(0)

def critical_print(*messages, action=None):
    if action is not None:
        action()

    err_time = datetime.now().isoformat().replace("T", " ")
    print(err_time, "|", *messages, file=sys.stderr)
    sys.exit()

def main():
    # handle unix signal before exiting
    signal.signal(signal.SIGTERM, signal_term_handler)
    signal.signal(signal.SIGINT, signal_term_handler)

    start_time = datetime.now().isoformat().replace("T", " ")
    print(start_time, '|', PROCESS_NAME, 'started')

    # parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--auth', default=["auth.conf"], nargs=1,
                        help="Path to file with auth settings.")
    parser.add_argument('-r', '--run', default=["run.conf"], nargs=1,
                        help="Path to file with run settings.")
    parser.add_argument('-n', '--no-notify', action='store_true', default=False,
                        help="Disable log notification messages (REPLIES).")
    command_arg = parser.parse_args()
    if command_arg.no_notify:
        NO_NOTIFY = True

    # set filenames for files with auth and run settings
    auth_filename = command_arg.auth[0]
    run_filename = command_arg.run[0]
    print("Auth file name: ", auth_filename)
    print("Run file name: ", run_filename)

    # load info from settings files
    auth_settings = load_auth_settings(auth_filename)
    run_settings = load_run_settings(run_filename)

    # reddit authentication
    try:
        my_username, subreddit = auth(auth_settings)
    except Exception as err:
        critical_print("Can't auth : ", err)

    # script main function executing
    try:
        process_comments_stream(my_username, subreddit, run_settings)
    except Exception as err:
        critical_print("Runtime error : ", err)

# reddit authentication, username and subreddit obtaining
# argument s - dict with auth settings
def auth(s: dict):
    reddit = praw.Reddit(user_agent=s.get("user_agent"),
                            client_id=s.get("client_id"), client_secret=s.get("client_secret"),
                            username=s.get("username"), password=s.get("password"))
    my_username = reddit.user.me()

    auth_time = datetime.now().isoformat().replace("T", " ")
    print(auth_time, "|", PROCESS_NAME, "authenticated, user name: '", my_username, "'")
    subreddit = reddit.subreddit(s.get("subreddit"))
    print("Subredit name: ", subreddit)
    return my_username, subreddit

# main sctipt function
def process_comments_stream(my_username:str, subreddit, run_settings: dict) -> None:

    compiled_search = re.compile(run_settings.get("search_name"), re.IGNORECASE)
    image_dict = run_settings.get("dict")
    separator = run_settings.get("separator")

    # process every comment obtained from reddit online stream
    for comment in subreddit.stream.comments(skip_existing=True):

        # don't process youself and deleted comments
        if (comment.author.name != my_username.name) and (comment.author is not None):
            comment_body = comment.body

            #find all files names in comment
            substitutes = compiled_search.findall(comment_body)

            answer_images = []
            #find every image_name in comment
            for substitute in substitutes:
                for phrase in substitute:
                    image_name_list = phrase.split(separator)
                    if len(image_name_list) > 1:
                        image_name = image_name_list[0].lower()

                        #remove delimeters
                        image_name = image_name.replace("-", "")
                        image_name = image_name.replace("_", "")

                        image_url_list = image_dict.get(image_name)

                        #add url into reply comment
                        if image_url_list is None:
                            image = (phrase, "{}(неизвестен)".format(phrase))
                            answer_images.append(image)

                            message_subject = "UNKNOWN IMAGE"
                            print("UNKNOWN IMAGE:", message_subject)
                            message_text = image_name + "\n\nwww.reddit.com{}".format(comment.permalink)
                            if not NO_NOTIFY:
                                reply_time = datetime.now().isoformat().replace("T", " ")
                                print(reply_time, "| UNKNOWN:", message_subject, ":", message_text)
                            my_user.message(message_subject, message_text)

                        else:
                            image_url = random.choice(image_url_list)
                            image = (phrase, "[{}]({})\n".format(phrase, image_url))
                            answer_images.append(image)

            if len(answer_images) > 0:
                # form user sentense with links
                answer_comment = comment_body
                for image in answer_images:
                    answer_comment = answer_comment.replace(image[0], image[1], 1)

                # prepend catch phrase when want to create reply
                answer_comment = "^(Бип-боп, я {} — бот.)\n\n".format(BOT_NAME) + answer_comment + "\n\n^([PikabuОбсуждение](https://www.reddit.com) [GitHub](https://github.com/IarcaniusI/bot-imagery))"

                if not NO_NOTIFY:
                    reply_time = datetime.now().isoformat().replace("T", " ")
                    print(reply_time, "| REPLY:", comment_body, ":", answer_comment)

                try:
                    comment.reply(answer_comment)
                except Exception as err:
                    print(reply_time, "| Can't send reply to user '", comment.author, "':", err)

            if run_settings.get("forward_reply"):
                parent = comment.parent()
                # parent of comment is another comment and not deleted
                if (type(parent) is praw.models.reddit.comment.Comment) and (parent.author is not None):
                    if parent.author.name == my_username.name:
                        pre_parent = parent.parent()
                        if (type(pre_parent) is praw.models.reddit.comment.Comment) and (pre_parent.author is not None):
                            # check, if there are no ignore expressions then forward reply message to author of comment
                            ignore_reply_count = 0
                            for ignore in run_settings.get("ignore_reply_compiled"):
                                if ignore.search(comment_body):
                                    ignore_reply_count += 1

                            if ignore_reply_count == 0:
                                message_subject = "BOT-{} FORWARD REPLY".format(BOT_NAME)
                                message_text = comment_body + "\n\nwww.reddit.com{}".format(comment.permalink)

                                if not NO_NOTIFY:
                                    reply_time = datetime.now().isoformat().replace("T", " ")
                                    print(reply_time, "| FORWARD REPLY:", message_subject, ":", message_text)

                                pre_parent.author.message(message_subject, message_text)


# parse JSON file with auth settings and check it
def load_auth_settings(filename: str) -> dict:
    # read settings from JSON file
    try:
        read_file = open(filename, "r")
    except Exception as err:
        critical_print("Can't open file '", filename, "' : ", err, action=read_file.close)
    else:
        try:
            auth_settings = json.load(read_file)
        except Exception as err:
            critical_print("Impossible to parse file '", filename, "' : ", err, action=read_file.close)
    finally:
        read_file.close()

    # check type of auth settings
    auth_params = ["user_agent", "client_id", "client_secret", "username", "password" ,"subreddit"]
    if type(auth_settings) is not dict:
        critical_print("Incorrect root element in file '", filename, "'")
    else:
        for auth_param in auth_params:
            if type(auth_settings.get(auth_param)) is not str:
                critical_print("Incorrect argument '", auth_param, "' in file '", filename, "'")

    return auth_settings

# parse JSON file with run settings and check it
def load_run_settings(filename: str) -> dict:
    # read settings from JSON file
    try:
        read_file = open(filename, "r")
    except Exception as err:
        critical_print("Can't open file '", filename, "' : ", err, action=read_file.close)
    else:
        try:
            run_settings = json.load(read_file)
        except Exception as err:
            critical_print("Impossible to parse file '", filename, "' : ", err, action=read_file.close)
    finally:
        read_file.close()

    # check type of run settings
    if type(run_settings) is not dict:
        critical_print("Incorrect root element in file '", filename, "'")
    else:
        first_dict = run_settings.get("dict")
        if type(first_dict) is not list:
            critical_print("Incorrect property 'dict' in file '", filename, "'")
        elif type(run_settings.get("search_name")) is not str:
            critical_print("Incorrect property 'search_name' in file '", filename, "'")
        elif type(run_settings.get("separator")) is not str:
            critical_print("Incorrect property 'separator' in file '", filename, "'")
        elif type(run_settings.get("forward_reply")) is not bool:
            critical_print("Incorrect property 'forward_reply' in file '", filename, "'")
        elif type(run_settings.get("ignore_reply")) is not list:
            critical_print("Incorrect property 'ignore_reply' in file '", filename, "'")
        else:

            for i, value in enumerate(run_settings.get("ignore_reply")):
                if type(value) is not str:
                    critical_print("Incorrect phrase number '", i, "' in 'ignore_reply' in file '", filename, "'")

            for i, rule in enumerate(first_dict):
                if type(rule) is not dict:
                    critical_print("Incorrect rule number '", i, "' in file '", filename, "'")
                else:
                    if type(rule.get("triggers")) is not list:
                        critical_print("Incorrect property 'triggers' in rule number '", i, "' in file '", filename, "'")
                    else:
                        for j, value in enumerate(rule.get("triggers")):
                            if type(value) is not str:
                                critical_print("Incorrect trigger number '", j, "' in rule number '", i, "' in file '", filename, "'")

                    if type(rule.get("images")) is not list:
                        critical_print("Incorrect property 'images' in rule number '", i, "' in file '", filename, "'")
                    else:
                        for j, value in enumerate(rule.get("images")):
                            if type(value) is not str:
                                critical_print("Incorrect image number '", j, "' in rule number '", i, "' in file '", filename, "'")

    # replace image_dict from settings
    image_dict = {}
    rules = run_settings.get("dict")
    for rule in rules:

        disable = rule.get("disable", False)
        if not disable:
            triggers = rule.get("triggers")
            images = rule.get("images")
            for trigger in triggers:
                image_name = trigger.lower()
                image_name = image_name.replace("_", "")
                image_name = image_name.replace("-", "")
                image_dict[image_name] = images

    # add compiled regexes 'ignore_replies'
    run_settings["ignore_reply_compiled"] = []
    for ignore in run_settings.get("ignore_reply"):
        compiled = re.compile(ignore, re.IGNORECASE)
        run_settings["ignore_reply_compiled"].append(compiled)

    run_settings["dict"] = image_dict
    return run_settings

if __name__ == "__main__":
    main()
