// Unmount rendered components after each test (Testing Library needs this without globals).
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);
