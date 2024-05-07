import json
import re

from openai import OpenAI, OpenAIError
import tiktoken
from flask import Response, jsonify

from flask import Blueprint

from app.config import Config
from app.decorators import query_params
import htmlmin

config = Config()
logger = Config.logger

MODEL_GPT35_16K = "gpt-3.5-turbo-0125"
MODEL_GPT4 = "gpt-4-1106-preview"
MAX_TOKENS_GPT4 = 16000
MAX_TOKENS_GPT35_16K = 16000
ERROR_INVALID_ELEMENT = "Invalid html element."

MODEL = MODEL_GPT35_16K


def is_prompt_length_valid(prompt):
    encoding = tiktoken.encoding_for_model(MODEL)
    num_tokens = len(encoding.encode(prompt))
    if config.ENVIRONMENT == "production":
        logger.log_struct(
            {"model": MODEL, "tokens": num_tokens},
            severity="INFO",
        )
    if MODEL == MODEL_GPT4:
        return num_tokens < MAX_TOKENS_GPT4
    elif MODEL == MODEL_GPT35_16K:
        return num_tokens < MAX_TOKENS_GPT35_16K
    else:
        raise ValueError("Unsupported model: " + MODEL)


def is_valid_html(source_code):
    # Regex pattern for HTML tags
    pattern = "^<(\w+).*?>.*$"
    return bool(re.match(pattern, source_code.strip(), flags=re.DOTALL))


def parse_html(source):
    try:
        pattern = r"<[ ]*script.*?\/[ ]*script[ ]*>"
        text = re.sub(
            pattern, "", source, flags=(re.IGNORECASE | re.MULTILINE | re.DOTALL)
        )
        html = htmlmin.minify(text, remove_comments=True, remove_empty_space=True)
    except:
        html = source
    return html


def call_openai_api(prompt, role, isStream, model="", key=""):
    global MODEL

    if key == "":
        key = config.API_KEY
        client = OpenAI(api_key=key, organization="org-vrjw201KSt5hgeiFuytTSaHb")
    else:
        client = OpenAI(api_key=key)
        if model:
            MODEL = model

    if not is_prompt_length_valid(prompt):
        if config.ENVIRONMENT == "production":
            logger.log_text("Prompt too large", severity="INFO")
        return jsonify({"error": "The prompt is too long."}), 413

    try:
        if config.ENVIRONMENT == "local":
            print(prompt)

        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": role},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            stream=isStream,
            user="TestCraftUser",
        )

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
        return jsonify({"error": str(e.message)}), e.status_code


api = Blueprint("api", __name__)


@api.route("/api/ping", methods=["GET"])
@query_params()
def ping():
    return jsonify({"pong": True}), 200


@api.route("/api/models", methods=["GET"])
@query_params()
def models(open_ai_api_key=""):
    if open_ai_api_key == "":
        open_ai_api_key = config.API_KEY
        client = OpenAI(api_key=open_ai_api_key, organization="org-vrjw201KSt5hgeiFuytTSaHb")
    else:
        client = OpenAI(api_key=open_ai_api_key)
    response = client.models.list()
    models_list = response.model_dump().get('data')
    return models_list, 200


@api.route("/api/generate-ideas", methods=["POST"])
@query_params()
def generate_ideas(source_code, stream=True, open_ai_api_key="", model=""):
    if not is_valid_html(source_code):
        return jsonify({"error": ERROR_INVALID_ELEMENT}), 400

    if config.ENVIRONMENT == "production":
        logger.log_struct(
            {"mode": "Ideas"},
            severity="INFO",
        )

    role = "You are a Software Test Consultant"

    prompt = f"""
        Generate test ideas based on the HTML element below. Think this step by step, as a real Tester would.
        Focus on user-oriented tests that do not refer to HTML elements such as divs or classes. 
        Include negative tests and creative test scenarios. 
        Format the output as unordered lists, with a heading for each required list, such as Positive Tests or Negative Tests. Don't include any other heading. 
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
def automate_tests(source_code, base_url, framework, language, pom=False, stream=True, open_ai_api_key="", model=""):
    if not is_valid_html(source_code):
        return jsonify({"error": ERROR_INVALID_ELEMENT}), 400

    if config.ENVIRONMENT == "production":
        logger.log_struct(
            {
                "mode": "Automate",
                "language": language,
                "framework": framework,
                "pom": pom,
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
        prompt += f"""
    Use playwright/test library.
    """

    if pom:
        prompt += f"""
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
    source_code, base_url, framework, language, ideas, pom=False, stream=True, open_ai_api_key="", model=""
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
        prompt += f"""
    Use playwright/test library.
    """

    if pom:
        prompt += f"""
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
            {"mode": "Ideas"},
            severity="INFO",
        )

    role = "You are an expert on Web Accessibility"

    prompt = f"""
        Check the HTML element below for accessibility issues according to WCAG 2.1.
        Think about this step by step. First, assess the element against each criterion. Then, report the result in the format specified below. 
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
        I have a Mocha test framework. I need you to create a regular expression to include in a grep command to run tests.

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

    response = call_openai_api(prompt, role, False, MODEL_GPT4, key=open_ai_api_key, model=model)
    return response.choices[0].message.content
