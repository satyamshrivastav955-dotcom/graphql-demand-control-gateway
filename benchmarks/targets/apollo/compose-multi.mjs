// node compose-multi.mjs name=url:file ...  > supergraph.graphql
import { readFileSync } from "node:fs";
import { composeServices } from "@apollo/composition";
import { parse } from "graphql";
const services = process.argv.slice(2).map((spec) => {
  const [name, rest] = [spec.slice(0, spec.indexOf("=")), spec.slice(spec.indexOf("=") + 1)];
  const i = rest.lastIndexOf("@");
  return { name, url: rest.slice(0, i), typeDefs: parse(readFileSync(rest.slice(i + 1), "utf8")) };
});
const result = composeServices(services);
if (result.errors?.length) { console.error(result.errors.map((e) => e.message).join("\n")); process.exit(1); }
process.stdout.write(result.supergraphSdl);
