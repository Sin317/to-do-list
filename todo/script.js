const taskInput = document.getElementById('taskInput');
const addButton = document.getElementById('addButton');
const taskList = document.getElementById('taskList');

function fetchTasks() {
    fetch('/tasks')
        .then(response => response.json())
        .then(data => {
            taskList.innerHTML = ''; // Clear existing list
            data.forEach(task => {
                const listItem = document.createElement('li');
                listItem.textContent = task;
                taskList.appendChild(listItem);
            });
        });
}

fetchTasks(); // Load tasks on page load

addButton.addEventListener('click', () => {
    const taskText = taskInput.value.trim();
    if (taskText) {
        fetch('/tasks', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ task: taskText })
        })
        .then(() => {
            taskInput.value = '';
            fetchTasks(); // Refresh the list
        });
    }
});