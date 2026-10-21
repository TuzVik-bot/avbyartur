"use client";

import { useState, type FormEvent } from "react";
import { checkVinFormat, type VinFormatResult } from "@/lib/vin-format";

export function VinFormatCheck() {
  const [vin, setVin] = useState("");
  const [result, setResult] = useState<VinFormatResult | null>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResult(checkVinFormat(vin));
    setVin("");
  }

  function handleChange(value: string) {
    setVin(value);
    setResult(null);
  }

  return (
    <>
      <form onSubmit={handleSubmit}>
        <label className="field" htmlFor="vin-format-input">
          <span>VIN, 17 символов</span>
          <input
            id="vin-format-input"
            type="text"
            inputMode="text"
            autoCapitalize="characters"
            autoComplete="off"
            autoCorrect="off"
            spellCheck={false}
            maxLength={32}
            value={vin}
            aria-describedby="vin-format-help"
            aria-invalid={result?.valid === false}
            onChange={(event) => handleChange(event.currentTarget.value)}
          />
        </label>
        <p id="vin-format-help">В поле можно вводить только номер для локальной проверки формата. VIN не отправляется на сервер и не сохраняется. После проверки поле очищается.</p>
        <button className="button button-primary" type="submit">Проверить формат</button>
      </form>
      <p role="status" aria-live="polite" aria-atomic="true">
        {result?.message ?? "Проверка выполнится только в этом браузере."}
      </p>
    </>
  );
}
