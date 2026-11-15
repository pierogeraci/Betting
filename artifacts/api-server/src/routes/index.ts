import { Router, type IRouter } from "express";
import healthRouter from "./health";
import workspaceRouter from "./workspace";
import sourcesRouter from "./sources";
import intelligenceRouter from "./intelligence";
import exportsRouter from "./exports";
import storageRouter from "./storage";

const router: IRouter = Router();

router.use(healthRouter);
router.use(storageRouter);
router.use(workspaceRouter);
router.use(sourcesRouter);
router.use(intelligenceRouter);
router.use(exportsRouter);

export default router;
