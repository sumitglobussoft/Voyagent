/**
 * Passport OCR helper.
 *
 * v0 stubs the ML layer — `extractPassport` returns a canned MRZ parse
 * in __DEV__ and an `ocr_not_configured` error otherwise. The real
 * `parseMrz` function is shipped and tested against ICAO 9303 TD-3
 * sample vectors.
 *
 * TODO: replace the stub with a real OCR provider. Candidates:
 *   - Google Cloud Vision (requires GCP credentials + network).
 *   - AWS Textract (requires AWS credentials + network).
 *   - On-device ML via react-native-mlkit-text-recognition (third-party,
 *     ejects from Expo managed workflow).
 *   - Azure Computer Vision Read API.
 *
 * The chosen provider must yield two strings for the two MRZ lines,
 * which we then hand to `parseMrz`.
 */

// Type-only import — expo-camera is a peer runtime dep. The tests mock
// this away so the runtime binding is not required.
// eslint-disable-next-line @typescript-eslint/consistent-type-imports
export type CameraCapturedPicture = {
  uri: string;
  width: number;
  height: number;
  base64?: string;
};

export interface PassportFields {
  document_number: string;
  surname: string;
  given_names: string;
  nationality: string; // ISO 3166-1 alpha-3
  date_of_birth: string; // YYYY-MM-DD
  sex: "M" | "F" | "X";
  expiration_date: string; // YYYY-MM-DD
  raw_mrz: string[]; // the two MRZ lines
}

export interface OcrResult {
  ok: boolean;
  fields: PassportFields | null;
  error?: string;
}

// Test hook: tests can flip this to simulate production behavior even
// though vitest runs under Node (where __DEV__ is typically true).
export const __test__ = {
  forceDev: null as boolean | null,
};

function isDev(): boolean {
  if (__test__.forceDev !== null) return __test__.forceDev;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const g = globalThis as any;
  return typeof g.__DEV__ === "boolean" ? g.__DEV__ : true;
}

export async function extractPassport(
  photo: CameraCapturedPicture,
): Promise<OcrResult> {
  // The photo arg is intentionally unused in v0. Keep the parameter so
  // the signature does not break when a real provider is wired in.
  void photo;

  if (isDev()) {
    // ICAO 9303 Appendix B specimen. Fully checksum-valid.
    const line1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<";
    const line2 = "L898902C<3UTO6908061F9406236ZE184226B<<<<<14";
    try {
      return { ok: true, fields: parseMrz(line1, line2) };
    } catch (err) {
      return {
        ok: false,
        fields: null,
        error: `stub_parse_failed:${(err as Error).message}`,
      };
    }
  }

  return {
    ok: false,
    fields: null,
    error: "ocr_not_configured",
  };
}

// ---------------------------------------------------------------------------
// ICAO 9303 TD-3 MRZ parser.
//
// TD-3 is the passport format: exactly two lines, each 44 characters.
//
// Line 1:
//   [0]     document code ('P' for passport)
//   [1]     type (usually '<' or a letter)
//   [2..4]  issuing state (ISO 3166-1 alpha-3, may contain '<')
//   [5..43] surname + '<<' + given names, filler '<'
//
// Line 2:
//   [0..8]   document number (9 chars)
//   [9]      document number check digit
//   [10..12] nationality (3 chars)
//   [13..18] date of birth YYMMDD
//   [19]     DOB check digit
//   [20]     sex (M/F/< which means X/unspecified)
//   [21..26] expiration YYMMDD
//   [27]     expiration check digit
//   [28..41] personal number (14 chars, may be '<')
//   [42]     personal number check digit (or '<')
//   [43]     composite check digit
// ---------------------------------------------------------------------------

const TD3_LINE_LEN = 44;

/** Weights cycle 7,3,1 across the input. */
function mrzCheckDigit(input: string): number {
  const weights = [7, 3, 1];
  let sum = 0;
  for (let i = 0; i < input.length; i++) {
    const ch = input[i];
    let v: number;
    if (ch >= "0" && ch <= "9") {
      v = ch.charCodeAt(0) - 48;
    } else if (ch >= "A" && ch <= "Z") {
      v = ch.charCodeAt(0) - 55; // A=10
    } else if (ch === "<") {
      v = 0;
    } else {
      throw new Error(`invalid MRZ character: ${JSON.stringify(ch)}`);
    }
    sum += v * weights[i % 3];
  }
  return sum % 10;
}

function parseMrzDate(yyMMdd: string, pivot: number): string {
  if (!/^\d{6}$/.test(yyMMdd)) {
    throw new Error(`invalid MRZ date: ${yyMMdd}`);
  }
  const yy = parseInt(yyMMdd.slice(0, 2), 10);
  const mm = parseInt(yyMMdd.slice(2, 4), 10);
  const dd = parseInt(yyMMdd.slice(4, 6), 10);
  if (mm < 1 || mm > 12 || dd < 1 || dd > 31) {
    throw new Error(`invalid MRZ date: ${yyMMdd}`);
  }
  // Two-digit year disambiguation: values <= pivot are 20xx, else 19xx.
  const fullYear = yy <= pivot ? 2000 + yy : 1900 + yy;
  const mmStr = mm.toString().padStart(2, "0");
  const ddStr = dd.toString().padStart(2, "0");
  return `${fullYear}-${mmStr}-${ddStr}`;
}

function stripFiller(s: string): string {
  return s.replace(/</g, " ").trim().replace(/\s+/g, " ");
}

/**
 * Parse a TD-3 (passport) MRZ line pair.
 *
 * Throws on wrong line length, unknown characters, bad date format, or
 * a failed check digit on document number, DOB, or expiration.
 *
 * The composite check digit is verified when all its inputs are
 * available; a failing composite also throws.
 */
export function parseMrz(line1: string, line2: string): PassportFields {
  if (line1.length !== TD3_LINE_LEN) {
    throw new Error(
      `invalid MRZ line1 length: expected ${TD3_LINE_LEN}, got ${line1.length}`,
    );
  }
  if (line2.length !== TD3_LINE_LEN) {
    throw new Error(
      `invalid MRZ line2 length: expected ${TD3_LINE_LEN}, got ${line2.length}`,
    );
  }

  // --- Line 1 ---
  if (line1[0] !== "P") {
    throw new Error(`invalid MRZ document code: ${line1[0]}`);
  }
  const issuingState = line1.slice(2, 5).replace(/</g, "");
  const nameField = line1.slice(5, 44);
  const sepIdx = nameField.indexOf("<<");
  if (sepIdx < 0) {
    throw new Error("invalid MRZ name field: no '<<' separator");
  }
  const surname = stripFiller(nameField.slice(0, sepIdx));
  const givenNames = stripFiller(nameField.slice(sepIdx + 2));

  // --- Line 2 ---
  const documentNumber = line2.slice(0, 9);
  const documentCheck = line2[9];
  const nationality = line2.slice(10, 13).replace(/</g, "");
  const dobRaw = line2.slice(13, 19);
  const dobCheck = line2[19];
  const sexChar = line2[20];
  const expRaw = line2.slice(21, 27);
  const expCheck = line2[27];
  const personalNumber = line2.slice(28, 42);
  const personalCheck = line2[42];
  const compositeCheck = line2[43];

  // Check digits. 'parseInt' on '<' yields NaN; compare char-wise.
  const expectDocCheck = mrzCheckDigit(documentNumber).toString();
  if (documentCheck !== expectDocCheck) {
    throw new Error(
      `bad document number check digit: got ${documentCheck}, expected ${expectDocCheck}`,
    );
  }
  const expectDobCheck = mrzCheckDigit(dobRaw).toString();
  if (dobCheck !== expectDobCheck) {
    throw new Error(
      `bad DOB check digit: got ${dobCheck}, expected ${expectDobCheck}`,
    );
  }
  const expectExpCheck = mrzCheckDigit(expRaw).toString();
  if (expCheck !== expectExpCheck) {
    throw new Error(
      `bad expiration check digit: got ${expCheck}, expected ${expectExpCheck}`,
    );
  }

  // Composite over document-number+check, DOB+check, expiration+check,
  // personal number+check.
  const compositeInput =
    documentNumber +
    documentCheck +
    dobRaw +
    dobCheck +
    expRaw +
    expCheck +
    personalNumber +
    personalCheck;
  const expectComposite = mrzCheckDigit(compositeInput).toString();
  if (compositeCheck !== expectComposite) {
    throw new Error(
      `bad composite check digit: got ${compositeCheck}, expected ${expectComposite}`,
    );
  }

  // DOB pivot: anything up to current two-digit year + small fudge is 20xx.
  // Use 30 (i.e. up to 2030) as a reasonable default for passports issued
  // today. Expiration is always future-leaning so use a higher pivot.
  const dob = parseMrzDate(dobRaw, 30);
  const expiration = parseMrzDate(expRaw, 79);

  let sex: PassportFields["sex"];
  if (sexChar === "M") sex = "M";
  else if (sexChar === "F") sex = "F";
  else if (sexChar === "X" || sexChar === "<") sex = "X";
  else throw new Error(`invalid MRZ sex: ${sexChar}`);

  return {
    document_number: documentNumber.replace(/</g, ""),
    surname,
    given_names: givenNames,
    nationality: nationality || issuingState,
    date_of_birth: dob,
    sex,
    expiration_date: expiration,
    raw_mrz: [line1, line2],
  };
}

// Re-export the check digit helper so tests can cover it directly.
export const __internal__ = { mrzCheckDigit, parseMrzDate };
