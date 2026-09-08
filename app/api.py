import json
import re

from openai import OpenAI, OpenAIError
import tiktoken
from flask import Response, g, jsonify, request

from flask import Blueprint

from app.config import Config
from app.decorators import query_params
import htmlmin

config = Config()
logger = Config.logger

DEFAULT_MODEL = "gpt-5.6-luna"
MODEL_SELECTION_ENABLED = False
SUPPORTED_MODELS = [
    {
        "name": "gpt-5.6-sol",
        "tokens": 128000,
        "label": "GPT-5.6 Sol"
    },
    {
        "name": "gpt-5.6-terra",
        "tokens": 128000,
        "label": "GPT-5.6 Terra"
    },
    {
        "name": "gpt-5.6-luna",
        "tokens": 128000,
        "label": "GPT-5.6 Luna"
    }
]
MAX_TOKENS = 16000
ERROR_INVALID_ELEMENT = "Invalid html element."


def get_model_by_name(name):
    for model in SUPPORTED_MODELS:
        if model["name"] == name:
            return model
    return {}


def is_o1_model_or_newer(model_name):
    """Check if the model is an o1 model or newer (o1, o2, o3, etc.)"""
    return "o1" in model_name or "o3" in model_name


def is_gpt_5_6_model(model_name):
    return model_name == "gpt-5.6" or model_name.startswith("gpt-5.6-")


def log_warning(message):
    if hasattr(logger, "log_text"):
        logger.log_text(message, severity="WARNING")
    else:
        logger.warning(message)


def is_prompt_length_valid(prompt, model=DEFAULT_MODEL):
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.encoding_for_model("gpt-4o")
        log_warning(f"Failed to get encoding for model {model}, falling back to gpt-4o")

    num_tokens = len(encoding.encode(prompt))
    if config.ENVIRONMENT == "production":
        logger.log_struct(
            {"model": model, "tokens": num_tokens},
            severity="INFO",
        )
    selected_model = get_model_by_name(model)
    max_tokens = selected_model.get("tokens", MAX_TOKENS)
    return num_tokens < max_tokens


def is_valid_html(source_code):
    # Regex pattern for HTML tags
    pattern = r"^<(\w+).*?>.*$"
    return bool(re.match(pattern, source_code.strip(), flags=re.DOTALL))


def parse_html(source):
    try:
        pattern = r"<[ ]*script.*?\/[ ]*script[ ]*>"
        text = re.sub(
            pattern, "", source, flags=(re.IGNORECASE | re.MULTILINE | re.DOTALL)
        )
        html = htmlmin.minify(text, remove_comments=True, remove_empty_space=True)
    except Exception as e:
        print(f"Error parsing HTML: {e}")
        html = source
    return html


def call_openai_api(prompt, role, isStream, model="", key=""):
    if not model:
        model = DEFAULT_MODEL

    if not key:
        key = config.API_KEY
        client = OpenAI(api_key=key, organization="org-vrjw201KSt5hgeiFuytTSaHb")  # Modify with your own organization
    else:
        client = OpenAI(api_key=key)

    if not is_prompt_length_valid(prompt, model):
        if config.ENVIRONMENT == "production":
            logger.log_text("Prompt too large", severity="INFO")
        return jsonify({"error": "The prompt is too long."}), 413

    print(f"Model: {model}")

    try:
        if model == "o1-mini":
            messages = [
                {"role": "user", "content": prompt},
            ]
        else:
            messages = [
                {"role": "developer", "content": role},
                {"role": "user", "content": prompt},
            ]

        body = {
            "model": model,
            "messages": messages,
            "stream": isStream,
            "user": "TestCraftUser",
        }

        if is_gpt_5_6_model(model):
            body["reasoning_effort"] = "medium"
        elif not is_o1_model_or_newer(model):
            body["temperature"] = 0.5

        response = client.chat.completions.create(**body)

        if not isStream:
            print(response)
            return response

        def generate():
            for part in response:
                filtered_chunk = {
                    "choices": part.model_dump().get("choices"),
                }
                yield f"data: {json.dumps(filtered_chunk)}\n\n".encode()

        return Response(generate(), mimetype="text/event-stream")
    except OpenAIError as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e.message)}), e.status_code


api = Blueprint("api", __name__)


@api.route("/api/ping", methods=["GET"])
@query_params()
def ping():
    return jsonify({"pong": True}), 200


@api.route("/api/models", methods=["GET"])
def models():
    open_ai_api_key = request.args.get("open_ai_api_key", "")
    if open_ai_api_key == "":
        open_ai_api_key = config.API_KEY
        client = OpenAI(
            api_key=open_ai_api_key, organization="org-vrjw201KSt5hgeiFuytTSaHb"
        )
    else:
        client = OpenAI(api_key=open_ai_api_key)
    response = client.models.list()
    models_list = response.model_dump().get("data")
    filtered_list = [
        {"label": f"{model['label']}", "id": model["name"]}
        for model in SUPPORTED_MODELS
        if any(model["name"] == openai_model["id"] for openai_model in models_list)
    ]
    response = {
        "models": filtered_list,
        "default_model": DEFAULT_MODEL,
        "model_selection_enabled": MODEL_SELECTION_ENABLED,
    }
    return response, 200


@api.route("/api/generate-ideas", methods=["POST"])
@query_params()
def generate_ideas(source_code, stream=True, open_ai_api_key="", model=""):
    if not is_valid_html(source_code):
        return jsonify({"error": ERROR_INVALID_ELEMENT}), 400

    if config.ENVIRONMENT == "production":
        logger.log_struct(
            {
                "mode": "Ideas",
                "model": model,
            },
            severity="INFO",
        )

    role = "You are a Software Test Consultant"

    prompt = f"""
        Generate test ideas based on the HTML element below. Think this step by step, as a real Tester would.
        Focus on user-oriented tests that do not refer to HTML elements such as divs or classes.
        Include negative tests and creative test scenarios.
        Format the output as unordered lists, with a heading for each required list, such as Positive Tests
         or Negative Tests. Don't include any other heading.
        HTML:
        ```
        {parse_html(source_code)}
        ```

        Format the output as the following example:
        Positive Tests:
        <Idea 1>

        Negative Tests:
        <Idea 1>

        Creative Test Scenarios:
        <Idea 1>
        """

    return call_openai_api(prompt, role, stream, key=open_ai_api_key, model=model)


@api.route("/api/automate-tests", methods=["POST"])
@query_params()
def automate_tests(
    source_code,
    base_url,
    framework,
    language,
    pom=True,
    stream=True,
    open_ai_api_key="",
    model="",
):
    if not is_valid_html(source_code):
        return jsonify({"error": ERROR_INVALID_ELEMENT}), 400

    if config.ENVIRONMENT == "production":
        logger.log_struct(
            {
                "mode": "Automate",
                "language": language,
                "framework": framework,
                "pom": pom,
                "model": model,
            },
            severity="INFO",
        )

    role = "You are a Test Automation expert"

    prompt = f"""
    Generate {framework} tests using {language} based on the html element below.
    Use {base_url} as the baseUrl. Generate as much tests as possible.
    Always try to add assertions.
    Do not include explanatory or introductory text. The output must be all {language} code.
    Format the code in a plain text format without using triple backticks.
    """

    if framework == "playwright":
        prompt += """
    Use playwright/test library.
    """

    if pom:
        prompt += """
    Create page object models and use them in the tests.
    Selectors must be encapsulated in properties. Actions must be encapsulated in methods.
    Include a comment to indicate where each file starts.
    """

    prompt += f"""
    Html:
    ```
    {parse_html(source_code)}
    ```
    """

    return call_openai_api(prompt, role, stream, key=open_ai_api_key, model=model)


@api.route("/api/automate-tests-ideas", methods=["POST"])
@query_params()
def automate_tests_ideas(
    source_code,
    base_url,
    framework,
    language,
    ideas,
    pom=True,
    stream=True,
    open_ai_api_key="",
    model="",
):
    if not is_valid_html(source_code):
        return jsonify({"error": ERROR_INVALID_ELEMENT}), 400

    if config.ENVIRONMENT == "production":
        logger.log_struct(
            {
                "mode": "Automate-Ideas",
                "language": language,
                "framework": framework,
                "pom": pom,
                "model": model,
            },
            severity="INFO",
        )

    role = "You are a Test Automation expert"
    line_tab = "\n\t"
    prompt = f"""
    Using the following html:

    Html:
    ```
    {parse_html(source_code)}
    ```

    Generate {framework} tests using {language} for the following Test Cases:

    TestCases:
    ```
        {line_tab.join(ideas)}
    ```

    Use {base_url} as the baseUrl.
    Always try to add assertions.
    Do not include explanatory or introductory text. The output must be all {language} code.
    Format the code in a plain text format without using triple backticks.
    """

    if framework == "playwright":
        prompt += """
    Use playwright/test library.
    """

    if pom:
        prompt += """
    Create page object models and use them in the tests.
    Selectors must be encapsulated in properties. Actions must be encapsulated in methods.
    Include a comment to indicate where each file starts.
    """

    return call_openai_api(prompt, role, stream, key=open_ai_api_key, model=model)


@api.route("/api/check-accessibility", methods=["POST"])
@query_params()
def check_accessibility(source_code, stream=True, open_ai_api_key="", model=""):
    if not is_valid_html(source_code):
        return jsonify({"error": ERROR_INVALID_ELEMENT}), 400

    if config.ENVIRONMENT == "production":
        logger.log_struct(
            {
                "mode": "Ideas",
                "model": model,
             },
            severity="INFO",
        )

    role = "You are an expert on Web Accessibility"

    prompt = f"""
        Check the HTML element below for accessibility issues according to WCAG 2.1.
        Think about this step by step. First, assess the element against each criterion.
        Then, report the result in the format specified below.
        For the criteria that cannot be assessed just by looking at the HTML, create accessibility tests.
        In the report, each criteria must be a link to the reference documentation.

        Html:
        ```
        {source_code}
        ```

        Format the output as the following example:
        - Issues
        - Conformance Level A -
        - Issue:
        - Criteria:
        - Solution:

        - Conformance Level AA -
        - Issue:
        - Criteria:
        - Solution:

        - Conformance Level AAA -
        - Issue:
        - Criteria:
        - Solution:

        - Suggested Tests
        - Test:
        - Criteria:
        - Test Details:
        """

    return call_openai_api(prompt, role, stream, key=open_ai_api_key, model=model)


@api.route("/api/get-regex-for-run", methods=["POST"])
@query_params()
def get_regex_for_run(tests, requirement, open_ai_api_key="", model=""):

    role = "You are a Test Automation expert"

    prompt = f"""
        I have a Mocha test framework.
        I need you to create a regular expression to include in a grep command to run tests.

        Below you will find two things:
        - A JSON with suites, each containing an array of test names.
        - A User Requirement to create the grep command

        You will have to do the following:
        1. Review each suite name. If directly related to the User Requirement, add it to the regular expression.
        2. Review each test name. If directly related to the User Requirement, add it to the regular expression.

        Only respond with the regular expression.
        If the User Requirement is not related to any suite or test, respond with ".*" to run all the tests.
        Use the format of the example response.

        Example response:
        Regex: Add User|Update User|Patch User

        JSON
        ```
        {tests}
        ```

        Requirement:
        {requirement}
        """

    response = call_openai_api(prompt, role, False, key=open_ai_api_key, model=model)
    return response.choices[0].message.content


# ─── v2 Endpoints (free tier with Google OAuth) ────────────────────────────────

from app.auth import require_auth
from app.firestore import get_or_create_user, get_daily_usage, increment_usage, is_limit_reached, DAILY_LIMIT

FREE_TIER_MODEL = "gpt-5.6-luna"


@api.route("/api/v2/ping", methods=["GET"])
def v2_ping():
    return jsonify({"pong": True, "version": 2}), 200


@api.route("/api/v2/stream", methods=["POST"])
@require_auth
def v2_stream():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "Request body is required."}), 400

    prompt = payload.get("prompt", "")
    system_message = payload.get("systemMessage", "")

    if not prompt:
        return jsonify({"error": "prompt is required."}), 400

    user = g.user

    # Check daily usage limit
    if is_limit_reached(user["googleId"]):
        return jsonify({
            "error": f"Daily generation limit reached ({DAILY_LIMIT}/day). Add your own API key for unlimited use."
        }), 429

    # Force the cost-optimized model for server-funded requests (defense in depth)
    model = FREE_TIER_MODEL

    if not is_prompt_length_valid(prompt, model):
        return jsonify({"error": "The prompt is too long."}), 413

    client = OpenAI(api_key=config.API_KEY, organization="org-vrjw201KSt5hgeiFuytTSaHb")

    try:
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ]

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            reasoning_effort="medium",
            user=f"free-tier:{user['googleId']}",
        )

        # Increment usage count
        increment_usage(user["googleId"])

        def generate():
            for part in response:
                filtered_chunk = {
                    "choices": part.model_dump().get("choices"),
                }
                yield f"data: {json.dumps(filtered_chunk)}\n\n".encode()

        return Response(generate(), mimetype="text/event-stream")
    except OpenAIError as e:
        return jsonify({"error": str(e.message)}), e.status_code


@api.route("/api/v2/auth/me", methods=["GET"])
@require_auth
def v2_auth_me():
    user = g.user
    get_or_create_user(user)
    daily_usage = get_daily_usage(user["googleId"])
    return jsonify({
        "user": {
            "email": user["email"],
            "name": user["name"],
            "picture": user["picture"],
        },
        "usage": {
            "count": daily_usage,
            "limit": DAILY_LIMIT,
        },
    }), 200
