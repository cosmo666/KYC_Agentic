# Conversational KYC Agent — FAQ

## What is KYC?
"Know Your Customer" is the process financial institutions use to verify who you are before opening an account or letting you transact. In India it's mandated by the RBI and typically requires checking your Aadhaar and PAN.

## Why do you need my Aadhaar?
Aadhaar is an Officially Valid Document under the RBI Master Direction. We use it to confirm your name, date of birth, gender, and address. We never store the first eight digits of your Aadhaar number — only the last four.

## Why do you need my PAN?
PAN is required for most regulated financial transactions in India. We use it to cross-check that the name and date of birth on your Aadhaar match.

## Why a selfie?
The selfie is compared to the photo on your Aadhaar card so we can confirm that the documents belong to you.

## Is my data safe?
Everything is stored locally in the backing Postgres database for this demo. No third-party services other than ipwhois.io (which only sees your IP address) are contacted. The full Aadhaar number is masked before storage or display.

## How long does it take?
The typical flow is under two minutes once you have your Aadhaar, PAN, and a camera ready.

## I got "flagged" — what does that mean?
A flagged decision means your submission was borderline and needs a human reviewer. In this demo there is no reviewer dashboard yet — you'd be contacted by the real institution in practice.

## Which documents are supported?
Aadhaar and PAN for this demo. Passport, driving licence, and voter ID support are on the roadmap.
