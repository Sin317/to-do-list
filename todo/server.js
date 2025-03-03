const express = require('express');
const bodyParser = require('body-parser');
const app = express();
const port = 3000;

app.use(bodyParser.json());
app.use(express.static('')); // Serve static files (index.html, etc.)

let tasks = [];

app.get('/tasks', (req, res) => {
    res.json(tasks);
});

app.post('/tasks', (req, res) => {
    const task = req.body.task;
    if (task) {
        tasks.push(task);
        res.json({ message: 'Task added' });
    } else {
        res.status(400).json({ error: 'Task content is required' });
    }
});

app.listen(port, () => {
    console.log(`Server listening at http://localhost:${port}`);
});