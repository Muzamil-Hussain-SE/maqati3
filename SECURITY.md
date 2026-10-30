# Security policy

## Reporting a problem

**Please do not open a public issue for a security problem.** Report it privately
through GitHub instead:

**[Report a vulnerability](https://github.com/PSchmitz-Valckenberg/maqati3/security/advisories/new)**

Only the maintainer sees the report. Please include what you found, how to reproduce it,
and what an attacker could do with it. We aim to answer within a week. Once the
problem is fixed, you will be credited in the advisory unless you would rather not be.

## What counts

Anything that breaks one of the promises this system makes, for example:

- uploading without the upload key, or reading someone else's pending upload;
- getting into the admin dashboard without being on the admin list, or acting as
  another admin;
- **making something public that the publication gates should hold back**: an entry
  whose attribution is *not sure*, a line that is not the scholar's own words, or a
  topic that is excluded. For this project, that is a security problem, not only a bug;
- injecting content that is shown as a scholar's words;
- reading secrets, other users' data, or files outside the upload area.

## What does not count

- Denial of service, load tests and floods.
- Social engineering of the people involved.
- Problems in the provisional host name or third-party services that we do not control.

## Testing

Please test against your own local copy (see
[*Run it locally*](README.md#run-it-locally)), not against the live server. Do not
upload real recordings to the live server for testing, and do not try to read or change
other people's data.

## Supported versions

Only `main` is supported; that is what runs on the server.
