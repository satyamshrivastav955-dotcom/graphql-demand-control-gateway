// Compose subgraph.graphql into supergraph.graphql (single subgraph named "demo").
//   node compose.mjs http://upstream:8001/graphql > supergraph.graphql
import { readFileSync } from "node:fs";
import { composeServices } from "@apollo/composition";
import { parse } from "graphql";

const url = process.argv[2] || "http://upstream:8001/graphql";
const typeDefs = parse(readFileSync(new URL("./subgraph.graphql", import.meta.url), "utf8"));
const result = composeServices([{ name: "demo", url, typeDefs }]);
if (result.errors?.length) {
  console.error(result.errors.map((e) => e.message).join("\n"));
  process.exit(1);
}
process.stdout.write(result.supergraphSdl);
