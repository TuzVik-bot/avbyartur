import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
const mocks=vi.hoisted(() => ({ session:vi.fn(), request:vi.fn() }));
vi.mock("@/lib/server",()=>({requireSession:mocks.session}));
vi.mock("@/lib/server-api",()=>({serverApiRequest:mocks.request}));
import Page from "./page";
it("does not fetch email for an ordinary account",async()=>{
  mocks.session.mockResolvedValue({user:{role:"user"}});mocks.request.mockReset();
  const html=renderToStaticMarkup(await Page({searchParams:Promise.resolve({})}));
  expect(html).toContain("Нет доступа");expect(mocks.request).not.toHaveBeenCalled();
});
it("renders mail as plain text and creates only a local recovery link",async()=>{
  mocks.session.mockResolvedValue({user:{role:"admin"}});mocks.request.mockReset();
  mocks.request.mockResolvedValueOnce({items:[]}).mockResolvedValueOnce({subject:"Восстановление доступа",body:"<script>bad()</script> Код: abcdefghijklmnopqrstuv"});
  const html=renderToStaticMarkup(await Page({searchParams:Promise.resolve({message:"abcdefghijklmnopqrstuv"})}));
  expect(html).toContain("&lt;script&gt;");expect(html).not.toContain("<script>bad");
  expect(html).toContain('href="/recover#token=abcdefghijklmnopqrstuv"');
});
