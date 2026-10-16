// Rotation budget and committee size are separate ABI fields. The installed
// SDK supports addTransaction with and without its optional validUntil field.
export function rotationBudget(raw) {
  if (raw === undefined || raw === '') return undefined;
  if (typeof raw !== 'string' || !/^[1-7]$/.test(raw)) {
    throw new Error('max rotations must be an integer from 1 to 7');
  }
  return Number(raw);
}

export function verifyRotationEncoding(decoded, expectedRotations, initialValidators) {
  if (decoded.functionName !== 'addTransaction' || !Array.isArray(decoded.args)
      || ![5, 6].includes(decoded.args.length)
      || (decoded.args.length === 6 && (typeof decoded.args[5] !== 'bigint' || decoded.args[5] <= 0n))
      || decoded.args[2] !== BigInt(initialValidators)
      || decoded.args[3] !== BigInt(expectedRotations)) {
    throw new Error('consensus rotation encoding changed the committee or rotation budget: '
      + JSON.stringify({functionName: decoded.functionName, arguments: decoded.args?.length,
        validators: String(decoded.args?.[2]), rotations: String(decoded.args?.[3]),
        expectedValidators: initialValidators, expectedRotations}));
  }
  return { initialValidators: Number(decoded.args[2]), consensusMaxRotations: Number(decoded.args[3]) };
}
