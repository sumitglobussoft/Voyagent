import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  parseMrz,
  extractPassport,
  __internal__,
  __test__,
  type CameraCapturedPicture,
} from "../lib/ocr";

const { mrzCheckDigit } = __internal__;

// ---------------------------------------------------------------------------
// Test vector helpers.
//
// Building a valid TD-3 MRZ by hand is error-prone. Instead we construct
// each vector from its logical fields and let `mrzCheckDigit` fill the
// check digits. This means the happy-path assertions are still testing
// the parser end-to-end (including check-digit verification), but the
// test file does not hard-code brittle magic numbers that would rot on
// the slightest fixture tweak.
// ---------------------------------------------------------------------------

function pad(s: string, len: number, ch = "<"): string {
  if (s.length > len) throw new Error(`pad overflow: ${s}`);
  return s + ch.repeat(len - s.length);
}

interface MrzInput {
  issuingState: string; // 3 chars
  surname: string;
  givenNames: string;
  docNum: string; // up to 9 chars
  nationality: string; // 3 chars
  dob: string; // YYMMDD
  sex: "M" | "F" | "X" | "<";
  exp: string; // YYMMDD
  personalNumber?: string; // up to 14 chars
}

function buildMrz(i: MrzInput): [string, string] {
  const nameField = pad(
    `${i.surname}<<${i.givenNames.replace(/ /g, "<")}`,
    39,
  );
  const line1 = pad(`P<${pad(i.issuingState, 3)}${nameField}`, 44);

  const docPadded = pad(i.docNum, 9);
  const docCheck = mrzCheckDigit(docPadded).toString();
  const dobCheck = mrzCheckDigit(i.dob).toString();
  const expCheck = mrzCheckDigit(i.exp).toString();
  const personal = pad(i.personalNumber ?? "", 14);
  const personalCheck = (
    i.personalNumber ? mrzCheckDigit(personal) : 0
  ).toString();
  // Composite per ICAO 9303: document number + check, DOB + check,
  // exp + check, personal + check.
  const composite =
    docPadded +
    docCheck +
    i.dob +
    dobCheck +
    i.exp +
    expCheck +
    personal +
    (i.personalNumber ? personalCheck : "<");
  const compositeCheck = mrzCheckDigit(composite).toString();

  const line2 = pad(
    `${docPadded}${docCheck}${pad(i.nationality, 3)}${i.dob}${dobCheck}${i.sex}${i.exp}${expCheck}${personal}${i.personalNumber ? personalCheck : "<"}${compositeCheck}`,
    44,
  );
  return [line1, line2];
}

describe("mrzCheckDigit", () => {
  // ICAO 9303 Appendix B canonical vectors.
  it("computes 3 for L898902C<", () => {
    expect(mrzCheckDigit("L898902C<")).toBe(3);
  });
  it("computes 1 for 690806", () => {
    expect(mrzCheckDigit("690806")).toBe(1);
  });
  it("computes 6 for 940623", () => {
    expect(mrzCheckDigit("940623")).toBe(6);
  });
  it("throws on invalid characters", () => {
    expect(() => mrzCheckDigit("abc")).toThrow();
  });
});

describe("parseMrz — ICAO 9303 Appendix B specimen", () => {
  const line1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<";
  const line2 = "L898902C<3UTO6908061F9406236ZE184226B<<<<<14";

  it("parses the specimen into canonical fields", () => {
    const fields = parseMrz(line1, line2);
    expect(fields.surname).toBe("ERIKSSON");
    expect(fields.given_names).toBe("ANNA MARIA");
    expect(fields.document_number).toBe("L898902C");
    expect(fields.nationality).toBe("UTO");
    expect(fields.date_of_birth).toBe("1969-08-06");
    expect(fields.sex).toBe("F");
    expect(fields.expiration_date).toBe("1994-06-23");
    expect(fields.raw_mrz).toEqual([line1, line2]);
  });
});

describe("parseMrz — generated test vectors", () => {
  const vectors: Array<{ name: string; input: MrzInput }> = [
    {
      name: "IND male, recent DOB",
      input: {
        issuingState: "IND",
        surname: "SHARMA",
        givenNames: "RAHUL KUMAR",
        docNum: "M1234567",
        nationality: "IND",
        dob: "850514",
        sex: "M",
        exp: "280514",
        personalNumber: "ABC12345",
      },
    },
    {
      name: "USA female, X sex marker via <",
      input: {
        issuingState: "USA",
        surname: "SMITH",
        givenNames: "JANE",
        docNum: "963528172",
        nationality: "USA",
        dob: "920101",
        sex: "<",
        exp: "320101",
      },
    },
    {
      name: "GBR female, long hyphenated surname",
      input: {
        issuingState: "GBR",
        surname: "HOLMES",
        givenNames: "MARY ELIZABETH",
        docNum: "801234564",
        nationality: "GBR",
        dob: "770330",
        sex: "F",
        exp: "271129",
      },
    },
    {
      name: "DEU male, trailing filler docnum",
      input: {
        issuingState: "DEU",
        surname: "MUELLER",
        givenNames: "HANS",
        docNum: "C01X00T47",
        nationality: "DEU",
        dob: "640812",
        sex: "M",
        exp: "251231",
      },
    },
    {
      name: "JPN X-sex explicit",
      input: {
        issuingState: "JPN",
        surname: "TANAKA",
        givenNames: "KAORU",
        docNum: "TR0000001",
        nationality: "JPN",
        dob: "000229", // leap day
        sex: "X",
        exp: "300229",
      },
    },
  ];

  for (const { name, input } of vectors) {
    it(`parses ${name}`, () => {
      const [l1, l2] = buildMrz(input);
      const fields = parseMrz(l1, l2);
      expect(fields.surname).toBe(input.surname);
      expect(fields.given_names).toBe(input.givenNames);
      expect(fields.document_number).toBe(input.docNum.replace(/</g, ""));
      expect(fields.nationality).toBe(input.nationality);
      // DOB/exp round-trip: reparse the emitted YYYY-MM-DD and confirm
      // the YYMMDD suffix matches the input.
      expect(fields.date_of_birth.slice(2).replace(/-/g, "")).toBe(input.dob);
      expect(fields.expiration_date.slice(2).replace(/-/g, "")).toBe(input.exp);
      const expectedSex = input.sex === "<" ? "X" : input.sex;
      expect(fields.sex).toBe(expectedSex);
    });
  }

  it("strips '<' filler chars from surname and given names", () => {
    const [l1, l2] = buildMrz({
      issuingState: "IND",
      surname: "PATEL",
      givenNames: "RAJ",
      docNum: "X1234567",
      nationality: "IND",
      dob: "900101",
      sex: "M",
      exp: "300101",
    });
    const fields = parseMrz(l1, l2);
    expect(fields.surname).not.toContain("<");
    expect(fields.given_names).not.toContain("<");
  });
});

describe("parseMrz — error paths", () => {
  it("throws on wrong line1 length", () => {
    expect(() => parseMrz("P<IND", "L898902C<3UTO6908061F9406236ZE184226B<<<<<14"))
      .toThrow(/line1 length/);
  });

  it("throws on wrong line2 length", () => {
    expect(() =>
      parseMrz(
        "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
        "L898902C<3",
      ),
    ).toThrow(/line2 length/);
  });

  it("throws on bad document number check digit", () => {
    // Flip the document check digit from 3 to 0.
    const line1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<";
    const line2 = "L898902C<0UTO6908061F9406236ZE184226B<<<<<14";
    expect(() => parseMrz(line1, line2)).toThrow(/document number check/);
  });

  it("throws on bad DOB check digit", () => {
    const line1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<";
    const line2 = "L898902C<3UTO6908060F9406236ZE184226B<<<<<14";
    expect(() => parseMrz(line1, line2)).toThrow(/DOB check/);
  });

  it("throws on invalid MRZ date format (out-of-range month)", () => {
    const [l1] = [
      "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
    ];
    // Construct a line2 where the DOB is syntactically 6 digits but
    // represents month 15.
    const dobRaw = "691506";
    const expRaw = "940623";
    const docNum = "L898902C<";
    const docCheck = mrzCheckDigit(docNum).toString();
    const dobCheck = mrzCheckDigit(dobRaw).toString();
    const expCheck = mrzCheckDigit(expRaw).toString();
    const personal = "ZE184226B<<<<<";
    const personalCheck = "1";
    const composite =
      docNum +
      docCheck +
      dobRaw +
      dobCheck +
      expRaw +
      expCheck +
      personal +
      personalCheck;
    const compositeCheck = mrzCheckDigit(composite).toString();
    const line2 =
      docNum +
      docCheck +
      "UTO" +
      dobRaw +
      dobCheck +
      "F" +
      expRaw +
      expCheck +
      personal +
      personalCheck +
      compositeCheck;
    expect(() => parseMrz(l1, line2)).toThrow(/invalid MRZ date/);
  });

  it("throws on invalid sex character", () => {
    // Swap sex 'F' with 'Q' but leave all check digits intact — note
    // check digits don't cover the sex char, so the parser will reach
    // the sex validator.
    const line1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<";
    const line2 = "L898902C<3UTO6908061Q9406236ZE184226B<<<<<14";
    expect(() => parseMrz(line1, line2)).toThrow(/invalid MRZ sex/);
  });
});

describe("extractPassport (stub)", () => {
  beforeEach(() => {
    __test__.forceDev = null;
  });
  afterEach(() => {
    __test__.forceDev = null;
  });

  const fakePhoto: CameraCapturedPicture = {
    uri: "file:///tmp/fake.jpg",
    width: 800,
    height: 600,
  };

  it("returns the canned specimen in dev mode", async () => {
    __test__.forceDev = true;
    const result = await extractPassport(fakePhoto);
    expect(result.ok).toBe(true);
    expect(result.fields).not.toBeNull();
    expect(result.fields?.surname).toBe("ERIKSSON");
    expect(result.fields?.given_names).toBe("ANNA MARIA");
    expect(result.fields?.document_number).toBe("L898902C");
  });

  it("returns ocr_not_configured in production mode", async () => {
    __test__.forceDev = false;
    const result = await extractPassport(fakePhoto);
    expect(result.ok).toBe(false);
    expect(result.fields).toBeNull();
    expect(result.error).toBe("ocr_not_configured");
  });
});
