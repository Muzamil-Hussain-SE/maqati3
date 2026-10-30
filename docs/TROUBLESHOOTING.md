Troubleshooting

This guide covers common problems you may encounter when setting up and running maqati3 locally.

If your problem isn't covered here, please check the project documentation or open an issue on GitHub.

1. Docker and database problems
Database container fails to start

Make sure Docker is installed and running.

Check the container status:

bash
docker compose ps


Check the database logs:

bash
docker compose logs db


If the database container exits unexpectedly, inspect the logs for the underlying error before restarting it.

Port 5432 is already in use

The default PostgreSQL port may already be occupied by another database instance.

You can configure a different port using the DB_PORT environment variable.

For example:

bash
DB_PORT=55432 docker compose up -d --wait db


Make sure your DATABASE_URL uses the same port:

bash
export DATABASE_URL=postgresql://maqati3:devonly@127.0.0.1:55432/maqati3

2. Backend problems
Database connection fails

Check the following:

The database container is running.
The PostgreSQL port is correct.
The database name and credentials match your local configuration.
The DATABASE_URL environment variable is set.

You can inspect the database logs with:

bash
docker compose logs db

Database migration fails

Make sure the database is running and that DATABASE_URL points to the correct database.

Run the migration command from the backend directory:

bash
uv run python -m maqati3 migrate


If the migration still fails, inspect the error message before attempting to modify the database manually.

Python dependencies fail to install

Make sure you have installed uv and are using Python 3.13.

From the backend directory, run:

bash
uv sync


If installation fails, check the error output and verify your Python and uv versions.

3. Media processing problems
ffmpeg or fpcalc cannot be found

maqati3 requires ffmpeg and fpcalc for its media-processing features.

On Ubuntu or Debian, install them with:

bash
sudo apt update
sudo apt install ffmpeg libchromaprint-tools


On macOS:

bash
brew install chromaprint ffmpeg


Verify that both commands are available:

bash
ffmpeg -version
fpcalc -version


If either command is unavailable, check that the installation directory is included in your system's PATH.

4. Frontend problems
Frontend dependencies fail to install

Make sure Node.js 22 is installed.

Navigate to the frontend directory:

bash
cd frontend
npm ci


If installation fails, check the npm error output and verify your Node.js version.

Frontend cannot communicate with the backend

Check that:

The backend server is running.
The frontend development server is running.
The backend is listening on the expected port.
The local proxy configuration is correct.

Start the backend using the documented development command:

bash
UPLOAD_KEY=dev STAGING_DIR=.staging uv run python -m maqati3 serve --port 8000


Then start the frontend in a separate terminal:

bash
cd frontend
npm run dev

5. Running tests
Backend tests are skipped

Some backend database and end-to-end tests require:

A running PostgreSQL database.
A valid DATABASE_URL.
ffmpeg.
fpcalc.

Without these dependencies, some tests are skipped.

Run backend tests using:

bash
cd backend
uv run pytest

Frontend tests fail

Run the frontend checks individually:

bash
cd frontend
npm test
npm run lint
npx tsc --noEmit


Check the output of each command to identify the failure.

6. Still having problems?

If you cannot resolve your issue:

Read the main README.
Check the CONTRIBUTING guide.
Search existing GitHub issues.
If the problem hasn't been reported, open a new issue.

When reporting a problem, include:

Your operating system.
Your Python and Node.js versions.
The command you executed.
The complete error message.
Steps to reproduce the problem.

Please remove passwords, API keys, database credentials, and other sensitive information before sharing logs.

Thank you for helping improve maqati3!
