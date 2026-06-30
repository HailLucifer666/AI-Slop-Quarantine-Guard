"""Curated popular-package lists for the typosquat detector (SQG007).

Methodology (published, reproducible — honesty rule): a hand-curated static set
of widely-installed, high-download packages per ecosystem — the names attackers
most often impersonate. Names are stored *normalized* (lower-case; PyPI ``_``→``-``)
so the matcher compares like-for-like. This is intentionally a small, well-known
core rather than an exhaustive top-N: a typosquat finding is ADVISORY only, so we
favour precision (few false alarms) over recall. Expanding this from a published
download-ranking feed is a backlog item.
"""

# PyPI — normalized (lower-case, '-' canonical).
PYPI_POPULAR = frozenset({
    "requests", "urllib3", "numpy", "pandas", "scipy", "flask", "django",
    "fastapi", "pydantic", "sqlalchemy", "boto3", "botocore", "setuptools",
    "wheel", "pip", "certifi", "charset-normalizer", "idna", "six",
    "python-dateutil", "pytz", "click", "jinja2", "markupsafe", "werkzeug",
    "pyyaml", "cryptography", "cffi", "pyparsing", "packaging", "attrs",
    "importlib-metadata", "typing-extensions", "colorama", "tqdm",
    "beautifulsoup4", "soupsieve", "lxml", "pillow", "matplotlib",
    "scikit-learn", "torch", "tensorflow", "keras", "transformers", "openai",
    "anthropic", "httpx", "aiohttp", "starlette", "uvicorn", "gunicorn",
    "celery", "redis", "pymongo", "psycopg2", "psycopg2-binary", "asyncpg",
    "pytest", "tox", "coverage", "black", "flake8", "mypy", "isort", "pylint",
    "rich", "typer", "poetry", "virtualenv", "wrapt", "more-itertools",
    "protobuf", "grpcio", "awscli", "paramiko", "docker", "kubernetes",
    "jsonschema", "marshmallow", "alembic", "greenlet", "websockets",
    "dnspython", "cachetools", "tenacity", "joblib", "regex", "sympy",
    "networkx", "seaborn", "plotly", "statsmodels", "nltk", "spacy", "gensim",
    "opencv-python", "imageio", "h5py", "numba", "dask", "pyarrow", "openpyxl",
    "chardet", "multidict", "yarl", "frozenlist", "anyio", "httpcore",
    "pluggy", "tomli", "filelock", "platformdirs", "zipp",
})

# npm — normalized (lower-case). Scoped names keep their @scope/ prefix.
NPM_POPULAR = frozenset({
    "lodash", "react", "react-dom", "express", "axios", "chalk", "commander",
    "debug", "request", "async", "moment", "bluebird", "underscore", "vue",
    "webpack", "@babel/core", "typescript", "eslint", "prettier", "jest",
    "mocha", "chai", "sinon", "jquery", "bootstrap", "classnames", "prop-types",
    "redux", "react-redux", "redux-thunk", "rxjs", "next", "nuxt", "vite",
    "rollup", "esbuild", "gulp", "grunt", "browserify", "dotenv", "cors",
    "body-parser", "cookie-parser", "morgan", "helmet", "passport",
    "jsonwebtoken", "bcrypt", "bcryptjs", "mongoose", "mongodb", "mysql",
    "mysql2", "pg", "sequelize", "ioredis", "socket.io", "ws", "node-fetch",
    "got", "superagent", "cheerio", "puppeteer", "playwright", "nodemon",
    "ts-node", "uuid", "semver", "glob", "minimatch", "rimraf", "mkdirp",
    "fs-extra", "yargs", "inquirer", "ora", "winston", "pino", "joi", "yup",
    "zod", "dayjs", "date-fns", "ramda", "immer", "styled-components",
    "tailwindcss", "postcss", "autoprefixer", "sass", "less", "core-js",
    "@types/node", "@types/react", "left-pad", "colors", "qs", "form-data",
    "mime-types", "http-errors", "iconv-lite", "safe-buffer",
})

POPULAR_BY_ECOSYSTEM = {"pypi": PYPI_POPULAR, "npm": NPM_POPULAR}
