export abstract class STTParserBase {
  protected abstract name: string

  protected abstract parse(buffer: Buffer | string): Promise<string | null>
}
