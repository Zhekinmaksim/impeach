// Wait for pipes to drain before the CLI exits, including large SDK receipts.
export async function writeLine(value) {
  await new Promise((resolve, reject) => {
    process.stdout.write(value + '\n', error => error ? reject(error) : resolve());
  });
}
