#!/bin/bash

function usage() {
    echo 1>&2 "Usage:"
    echo 1>&2 "  $0 start|stop [-d] [-x]"
    echo 1>&2 "     [ -n count (5) ]"
    echo 1>&2 "     [ -e base_url (http://localhost:8000) ]"
    echo 1>&2 "     [ -l base_username (lsptestuser) ]"
    echo 1>&2 "     [ -u zero_indexed_base_uid (60180) ]"
    echo 1>&2 "     [ -t user_template_file (./user_template.json) ]"
    echo 1>&2 "  # -d enables debugging output"
    echo 1>&2 "  # -x is dry-run: do not send network traffic"
    echo 1>&2 "  # if not dry-run, ACCESS_TOKEN env var must be set to a"
    echo 1>&2 "  #  token allowing mobu use"
}

function our_realpath() {
    # https://stackoverflow.com/questions/3572030
    [[ $1 = /* ]] && echo "$1" || echo "$PWD/${1#./}"
}

function make_working_dir() {
    WORKDIR=$(mktemp -d -t mobu)
    if [ -z "${WORKDIR}" ]; then
	echo 1>&2 "Could not create working directory!"
	exit 2
    fi
    trap "rm -rf ${WORKDIR}" EXIT  # Clean up on exit
}

function monkey_massacre() {
    local uname=""
    for i in $(seq 1 $COUNT); do
	uname=$(printf "${UNAME_BASE}%0${DIGITS}d" ${i})
	$CURL -X DELETE "${MOBU_EP}/${uname}"
    done
}

function launch_monkeys() {
    local uname=""
    local uid=65535
    for i in $(seq 1 $COUNT); do
	uname=$(printf "${UNAME_BASE}%0${DIGITS}d" ${i})
	uid=$(( UID_BASE + i ))
	write_monkey_spec $uname $uid
	op=$($CURL -X POST -d@${uname}.json ${MOBU_EP})
	rc=$?
	if [ ${rc} -ne 0 ]; then
	    echo 1>&2 "User creation failed: ${rc}"
	    echo 1>&2 "Output was $(echo ${op} | ${JQ})"
	fi
    done
}

function write_monkey_spec {
    local uname=$1
    local uid=$2
    local fname="$1.json"
    sed -e "s/{{USERNAME}}/${uname}/" \
	-e "s/{{UID}}/${uid}/" \
	${TEMPLATE_FILE} > ${fname}
}

# Begin mainline code

# Set up default values
COUNT=5
ENDPOINT="http://localhost:8000"
UNAME_BASE="lsptestuser"
UID_BASE=60180
DEBUG=0
DRYRUN=0
TEMPLATE="./user_template.json"
REALPATH="realpath"
JQ="jq -M ."

# Pre-flight check: we need realpath, which is not present by default on MacOS
realpath $0 2>&1 >/dev/null
rc=$?
if [ ${rc} -ne 0 ]; then
    # fake it with a shell function
    REALPATH=our_realpath
fi
# If we don't have jq, try python.  If we don't have python either, just
# give up on pretty printing it with, yes, a useless use of cat
echo '{}' | $JQ 2>&1 >/dev/null
rc=$?
if [ ${rc} -ne 0]; then
    JQ="python -m json.tool"
    echo '{}' | $JQ 2>&1 >/dev/null
    rc=$?
    if [ ${rc} -ne 0 ]; then
	JQ="cat"
    fi
fi

# Make sure we have either "start" or "stop" as our command
COMMAND=$1
shift
case ${COMMAND} in
    start|stop )
	:
	;;
    * )
	usage
	exit 1
esac

# Parse our options
while getopts ":hdxn:e:l:u:" opts; do
    case ${opts} in
	h )
	    usage
	    exit 0
	    ;;
	n )
	    COUNT=$OPTARG
	    if [ $COUNT -ge 1 ] 2>/dev/null ; then
		:
	    else
		echo 1>&2 "-n argument must be a positive integer"
		exit 1
	    fi
	    ;;
	e )
	    ENDPOINT=$OPTARG
	    ;;
	l )
	    UNAME_BASE=$OPTARG
	    ;;
	u )
	    UID_BASE=$OPTARG
	    if [ $UID_BASE -ge 0 ] 2>/dev/null ; then
		:
	    else
		echo 1>&2 "-u argument must be a non-negative integer"
		exit 1
	    fi
	    ;;
	t )
	    TEMPLATE=$OPTARG
	    ;;
	d )
	    DEBUG=1
	    ;;
	x )
	    DRYRUN=1
	    ;;
	\? )
	    usage
	    exit 1
	    ;;
    esac
done
shift $((OPTIND - 1))

# Now we have the necessary information to manipulate the monkeys
if [ ${DEBUG} -ne 0 ]; then
    set -x  # Turn on verbose output
fi
if [ ${DRYRUN} -ne 0 ]; then
    CURL="echo curl"  # Don't actually make network calls
else
    # If we are making calls, check for access token
    if [ -z "${ACCESS_TOKEN}" ]; then
	echo 1>&2 "ACCESS_TOKEN must contain a token allowing mobu use."
	exit 1
    fi
    CURL="curl -u ${ACCESS_TOKEN}:"
fi
    
DIGITS=${#COUNT}
if [ $DIGITS -lt 2 ]; then
   DIGITS=2  # To preserve compatibility with existing implementation
fi
TEMPLATE_FILE=$($REALPATH $TEMPLATE)
if [ -z "${TEMPLATE_FILE}" ]; then
    echo 1>&2 "Cannot find user template file at ${TEMPLATE}"
    exit 1
fi
MOBU_EP="${ENDPOINT}/mobu/user"

make_working_dir
cd $WORKDIR
if [ "${COMMAND}" == "stop" ]; then
    monkey_massacre
else
    launch_monkeys
fi
# End of mainline code; implicit exit rc=0
