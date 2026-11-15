import { Router, type IRouter } from "express";
import { GetSessionResponse } from "@workspace/api-zod";
import healthRouter from "./health";
import workspaceRouter from "./workspace";
import sourcesRouter from "./sources";
import intelligenceRouter from "./intelligence";
import exportsRouter from "./exports";
import storageRouter from "./storage";
import {
  currentIdentity,
  loadWorkspaceUser,
  requireActiveMember,
  requireSignedIn,
} from "../lib/auth";

const router: IRouter = Router();

router.use(healthRouter);
router.get(
  "/session",
  requireSignedIn,
  loadWorkspaceUser,
  (req, res): void => {
    const identity = currentIdentity(req);
    const user = req.ctiUser;
    if (!identity || !user) {
      res.status(401).json({ error: "Sign-in required" });
      return;
    }
    const accessState =
      user.status === "active"
        ? "active"
        : user.status === "disabled"
          ? "disabled"
          : "pending";
    res.json(
      GetSessionResponse.parse({
        authenticated: true,
        userId: user.clerkUserId,
        displayName: user.displayName,
        email: user.email ?? identity.email,
        role: user.role,
        accessState,
      }),
    );
  },
);
router.use(storageRouter);
router.use(requireActiveMember);
router.use(workspaceRouter);
router.use(sourcesRouter);
router.use(intelligenceRouter);
router.use(exportsRouter);

export default router;
